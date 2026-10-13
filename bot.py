"""
Odds Bot — παρακολουθεί πτώσεις αποδόσεων σε sharp bookmakers (Pinnacle, Betfair Exchange)
και ευκαιρίες αξίας σε ελληνικούς bookmakers, προαγωνιστικά και live. Ειδοποιεί στο Telegram.

Χρήση:
    python bot.py                 # κανονικός γύρος
    python bot.py --dry-run       # τυπώνει τις ειδοποιήσεις αντί να τις στέλνει
    python bot.py --test-telegram # στέλνει δοκιμαστικό μήνυμα
    python bot.py --quota         # δείχνει πόσα αιτήματα έχουν μείνει
    python bot.py --leagues       # δείχνει τις λίγκες και ποιες παρακολουθούνται
    python bot.py --markets       # δείχνει ποιες αγορές βρέθηκαν στο API
"""
from __future__ import annotations

import datetime as dt
import html
import json
import logging
import os
import re
import sys
import time
import unicodedata

import requests
from zoneinfo import ZoneInfo

import config as C

API = "https://api.oddspapi.io/v4"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
ATHENS = ZoneInfo("Europe/Athens")
COOLDOWN = {"historical-odds": 5.1, "fixtures": 2.3, "markets": 1.2, "account": 1.2}
GR_DAYS = ["Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ"]
BETFAIR = "betfair-ex"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("odds-bot")


class QuotaExceeded(Exception):
    pass


# ----------------------------------------------------------------- API ---------
_last_call: dict[str, float] = {}


def api_get(endpoint: str, **params):
    """GET με σεβασμό στο cooldown κάθε endpoint και επανάληψη σε προσωρινά σφάλματα."""
    params["apiKey"] = C.ODDSPAPI_KEY
    r = None
    for attempt in range(4):
        wait = COOLDOWN.get(endpoint, 1.2) - (time.monotonic() - _last_call.get(endpoint, -1e9))
        if wait > 0:
            time.sleep(wait)
        r = requests.get(f"{API}/{endpoint}", params=params, timeout=40)
        _last_call[endpoint] = time.monotonic()
        if r.status_code == 429:
            if "REQUEST_LIMIT_EXCEEDED" in r.text:
                raise QuotaExceeded(r.text)
            time.sleep(6 * (attempt + 1))
            continue
        if r.status_code >= 500:
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise requests.HTTPError(f"{r.status_code} από {endpoint}: {r.text[:300]}", response=r)
        return r.json()
    r.raise_for_status()
    raise RuntimeError(f"{endpoint}: απέτυχε μετά από επαναλήψεις ({r.status_code})")


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(text) -> str:
    """Πεζά, χωρίς τόνους (Süper → super, Série → serie), με - και _ ως κενό."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", t.lower())).strip()


# --------------------------------------------------------------- State ---------
def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)


# ------------------------------------------------------------- Αγορές ---------
def refresh_markets(state: dict, now: dt.datetime) -> None:
    fetched = state.get("markets_fetched_at")
    if state.get("market_catalog") and fetched and \
            now - parse_ts(fetched) < dt.timedelta(days=C.MARKETS_REFRESH_DAYS):
        return
    log.info("Ανανέωση καταλόγου αγορών (1 αίτημα από το μηνιαίο όριο)")
    data = api_get("markets", language="en")
    catalog = []
    for m in data if isinstance(data, list) else []:
        if m.get("sportId") not in (10, None) or m.get("playerProp"):
            continue
        catalog.append({k: m.get(k) for k in
                        ("marketId", "marketName", "handicap", "period", "marketType", "outcomes")})
    state["market_catalog"] = catalog
    state["markets_fetched_at"] = iso(now)
    log.info("Κατάλογος: %d αγορές ποδοσφαίρου", len(catalog))


def _period_ok(m: dict, want: str) -> bool:
    p, name = norm(m.get("period")), norm(m.get("marketName"))
    first_half = any(x in p for x in ("first", "1st", "half1", "1h", "h1", "p1")) or \
        any(x in name for x in ("1st half", "first half", "half time", "halftime"))
    if want == "half1":
        return first_half
    return not first_half and not any(x in p or x in name for x in
                                      ("2nd", "second", "extra", "overtime", "penalt"))


def _excluded(m: dict) -> bool:
    name = norm(m.get("marketName"))
    return any(x in name for x in ("corner", "card", "booking", "team", "player", "asian",
                                   "home", "away", "minute", "both"))


def resolve_markets(catalog: list[dict]) -> dict:
    """Από τον κατάλογο του API βρίσκει τους κωδικούς για τις αγορές του config.MARKETS."""
    resolved: dict[str, dict] = {}
    for cfg in C.MARKETS:
        for m in catalog:
            mid = str(m.get("marketId"))
            name = norm(m.get("marketName"))
            outs = {str(o.get("outcomeId")): str(o.get("outcomeName") or "")
                    for o in (m.get("outcomes") or [])}
            if not outs or not _period_ok(m, cfg["period"]):
                continue
            kind = cfg["kind"]
            if kind == "1x2":
                ok = mid == "101" or (norm(m.get("marketType")) == "1x2" and cfg["period"] == "half1")
            elif kind == "totals":
                is_ou = any(norm(n) in ("over", "under") for n in outs.values()) or "over under" in name
                try:
                    line = float(m.get("handicap"))
                except (TypeError, ValueError):
                    line = None
                ok = is_ou and not _excluded(m) and line in cfg.get("lines", [])
            elif kind == "correct_score":
                ok = ("correct score" in name or "exact score" in name) and "team" not in name \
                    and sum(":" in n for n in outs.values()) >= 0.6 * len(outs)
            else:
                ok = False
            if ok and mid not in resolved:
                title = cfg["name"]
                if kind == "totals" and len(cfg.get("lines", [])) > 1:
                    title += f" ({float(m['handicap']):g})"
                resolved[mid] = {"name": title, "kind": kind, "outcomes": outs,
                                 "line": m.get("handicap"),
                                 "max_odds": cfg.get("max_odds", C.MAX_ODDS)}
    if not resolved:  # ασφάλεια: τουλάχιστον το 1Χ2 που ξέρουμε από τα docs
        resolved["101"] = {"name": "Τελικό αποτέλεσμα 1Χ2", "kind": "1x2", "line": 0,
                           "outcomes": {"101": "1", "102": "X", "103": "2"}, "max_odds": C.MAX_ODDS}
    return resolved


# ------------------------------------------------------------ Fixtures ---------
def refresh_fixtures(state: dict, now: dt.datetime) -> None:
    fetched = state.get("fixtures_fetched_at")
    old_format = any("tournamentId" not in f for f in state.get("fixtures", []))
    if fetched and not old_format and \
            now - parse_ts(fetched) < dt.timedelta(hours=C.FIXTURE_REFRESH_HOURS):
        return
    log.info("Ανανέωση λίστας αγώνων (1 αίτημα από το μηνιαίο όριο)")
    data = api_get(
        "fixtures", sportId=10, statusId=0, hasOdds="true", bookmakers=C.SHARP_BOOK,
        **{"from": iso(now), "to": iso(now + dt.timedelta(hours=47))},
    )
    keep = ("fixtureId", "startTime", "tournamentId", "participant1Name", "participant2Name",
            "participant1ShortName", "participant2ShortName",
            "tournamentName", "tournamentSlug", "categorySlug", "categoryName")
    new = [{k: f.get(k) for k in keep} for f in data]
    # Κρατάμε αγώνες που ξεκίνησαν πρόσφατα (live) από την προηγούμενη λίστα
    live_cut = now - dt.timedelta(minutes=C.LIVE_MAX_MINUTES)
    ids = {f["fixtureId"] for f in new}
    for f in state.get("fixtures", []):
        if f.get("fixtureId") not in ids and f.get("startTime") and \
                live_cut < parse_ts(f["startTime"]) <= now:
            new.append(f)
    state["fixtures"] = new
    state["fixtures_fetched_at"] = iso(now)
    log.info("Βρέθηκαν %d αγώνες ποδοσφαίρου τις επόμενες 47 ώρες", len(data))


def league_ok(f: dict) -> bool:
    name_ = norm(f.get("tournamentName"))
    text = f"{norm(f.get('tournamentSlug'))} {name_}"
    if any(k.strip() and norm(k) in text for k in C.EXCLUDE_KEYWORDS):
        return False
    try:
        if int(f.get("tournamentId")) in C.EXTRA_LEAGUE_IDS:
            return True
    except (TypeError, ValueError):
        pass
    if any(re.search(p, name_) for p in C.CUPS):
        return True
    if not C.COUNTRY_LEAGUES:
        return True
    country = {norm(f.get("categorySlug")), norm(f.get("categoryName"))}
    for aliases, patterns in C.COUNTRY_LEAGUES.items():
        if country & {norm(a) for a in aliases}:
            return any(re.search(p, name_) for p in patterns)
    return False


def is_live(f: dict, now: dt.datetime) -> bool:
    start = parse_ts(f["startTime"])
    return start <= now < start + dt.timedelta(minutes=C.LIVE_MAX_MINUTES)


def live_can_alert() -> bool:
    """Στα live δεν μετράμε πτώσεις → βγάζουν το πολύ ⭐. Αν θέλουμε ⭐⭐+, ο έλεγχός τους είναι χαμένος χρόνος."""
    return C.LIVE_ENABLED and (C.LIVE_DROPS or C.MIN_STARS <= 1)


def check_interval_min(start: dt.datetime, now: dt.datetime) -> float:
    """Κάθε πόσα λεπτά ελέγχεται ένας αγώνας, ανάλογα με το πόσο κοντά είναι η σέντρα.
    Οι περισσότερες κινήσεις γίνονται τις τελευταίες ώρες → εκεί ελέγχουμε πιο συχνά."""
    hours = (start - now).total_seconds() / 3600
    for limit_h, every in C.CHECK_TIERS:
        if hours <= limit_h:
            return every
    return C.CHECK_TIERS[-1][1]


def select_fixtures(state: dict, now: dt.datetime) -> list[dict]:
    """1) Όσοι αγώνες "χρωστάνε" έλεγχο (ανάλογα με το πόσο κοντά είναι η σέντρα), με προτεραιότητα
    στους πιο κοντινούς και σε όσους ελέγχθηκαν παλιότερα. 2) Αν περισσεύει χρόνος, οι υπόλοιποι
    εκ περιτροπής. Οι live μόνο αν μπορούν να βγάλουν ειδοποίηση."""
    horizon = now + dt.timedelta(hours=C.LOOKAHEAD_HOURS)
    checked = state.get("checked", {})
    use_live = live_can_alert()
    due, rest, live = [], [], []
    for f in state.get("fixtures", []):
        if not f.get("startTime") or not league_ok(f):
            continue
        start = parse_ts(f["startTime"])
        if use_live and is_live(f, now):
            live.append(f)
            continue
        if not now < start <= horizon:
            continue
        last = checked.get(f["fixtureId"])
        age = (now - parse_ts(last)).total_seconds() / 60 if last else 1e9
        (due if age >= check_interval_min(start, now) - 1 else rest).append(f)
    key = lambda f: (checked.get(f["fixtureId"], ""), f["startTime"])
    due.sort(key=lambda f: (check_interval_min(parse_ts(f["startTime"]), now), key(f)))
    rest.sort(key=key)
    live.sort(key=key)
    out = live + due + rest
    log.info("%d αγώνες στο παράθυρο · %d χρειάζονται έλεγχο τώρα (%d live)",
             len(due) + len(rest) + len(live), len(due), len(live))
    return out[: C.MAX_FIXTURES]


def fix_slugs(books: list[str], error_text: str) -> dict[str, str]:
    """Από το μήνυμα λάθους του API ('Invalid bookmakers: X. Valid bookmakers are: a, b, ...')
    βρίσκει το σωστό όνομα για κάθε λάθος bookmaker."""
    m = re.search(r"Invalid bookmakers?:\s*([^.]+?)\.\s*Valid bookmakers are:\s*(.+?)[\"}]", error_text)
    if not m:
        return {}
    bad = [b.strip() for b in m.group(1).split(",")]
    valid = [v.strip() for v in m.group(2).split(",") if v.strip()]
    fixes = {}
    for b in bad:
        if b not in books:
            continue
        root = norm(re.split(r"[-.]", b)[0])
        cands = [v for v in valid if norm(v).startswith(root)] or [v for v in valid if root in norm(v)]
        cands.sort(key=lambda v: (".gr" not in v and "-gr" not in v, len(v)))
        if cands:
            fixes[b] = cands[0]
    return fixes


def apply_slug_fixes(fixes: dict[str, str]) -> None:
    for old, new in fixes.items():
        C.GREEK_BOOKS[:] = [new if b == old else b for b in C.GREEK_BOOKS]
        C.BOOK_NAMES.setdefault(new, C.BOOK_NAMES.get(old, new))


def fetch_history(fixture_id: str, state: dict | None = None) -> dict:
    books = [C.SHARP_BOOK] + C.GREEK_BOOKS[:2]
    try:
        data = api_get("historical-odds", fixtureId=fixture_id, bookmakers=",".join(books))
    except requests.HTTPError as e:
        text = e.response.text if e.response is not None else str(e)
        fixes = fix_slugs(books, text)
        if not fixes:
            raise
        log.warning("Διόρθωση ονομάτων bookmaker: %s (άλλαξέ τα και στο config.py)", fixes)
        apply_slug_fixes(fixes)
        if state is not None:
            state.setdefault("slug_fix", {}).update(fixes)
        books = [C.SHARP_BOOK] + C.GREEK_BOOKS[:2]
        data = api_get("historical-odds", fixtureId=fixture_id, bookmakers=",".join(books))
    merged = dict(data.get("bookmakers") or {})
    if C.USE_BETFAIR:
        try:
            bf = api_get("historical-odds", fixtureId=fixture_id, bookmakers=BETFAIR)
            merged.update(bf.get("bookmakers") or {})
        except QuotaExceeded:
            raise
        except Exception as e:  # το Betfair είναι προαιρετικό
            log.warning("Betfair για %s: %s", fixture_id, e)
    return merged


def merge_betfair(hist: dict, data: dict) -> int:
    """Προσθέτει στο hist τα δεδομένα Betfair ενός αποτελέσματος, αγνοώντας τιμές με λίγα λεφτά
    (κάτω από BETFAIR_MIN_LIQUIDITY), που κινούνται χωρίς λόγο. Επιστρέφει πόσες εγγραφές κράτησε."""
    kept = 0
    for bm in (data.get("bookmakers") or {}).values():
        for mid, mk in (bm.get("markets") or {}).items():
            for oid, oc in (mk.get("outcomes") or {}).items():
                rows = [r for r in ((oc.get("players") or {}).get("0") or [])
                        if (r.get("limit") or 0) >= C.BETFAIR_MIN_LIQUIDITY]
                if not rows:
                    continue
                dst = hist.setdefault(BETFAIR, {}).setdefault("markets", {}) \
                    .setdefault(mid, {}).setdefault("outcomes", {})
                dst[oid] = {"players": {"0": rows}}
                kept += len(rows)
    return kept


def sharp_sources() -> list[str]:
    return [C.SHARP_BOOK, BETFAIR] + list(C.CONFIRM_BOOKS)


def fetch_confirmations(fx: dict, hist: dict, sigs: list[dict], state: dict) -> list[str]:
    """Μόνο όταν υπάρχει ήδη σήμα αξίας: φέρνει 2η/3η/4η πηγή για επιβεβαίωση.
    - Ασιατικοί sharp (SBOBet, Singbet): 1 αίτημα για όλους μαζί
    - Betfair: 1 αίτημα ανά αποτέλεσμα με σήμα (όριο δωρεάν πλάνου)
    Το ιστορικό αποδόσεων δεν χρεώνεται στο μηνιαίο όριο. Επιστρέφει ποιες πηγές βρέθηκαν."""
    fid = fx["fixtureId"]
    books = [b for b in C.CONFIRM_BOOKS if b not in state.get("bad_books", [])]
    if books:
        try:
            data = api_get("historical-odds", fixtureId=fid, bookmakers=",".join(books[:3]))
            for b, v in (data.get("bookmakers") or {}).items():
                hist[b] = v
        except QuotaExceeded:
            raise
        except requests.HTTPError as e:
            text = e.response.text if e.response is not None else str(e)
            m = re.search(r"Invalid bookmakers?:\s*([^.]+?)\.", text)
            if m:  # λάθος όνομα bookmaker → το θυμόμαστε και δεν το ξαναζητάμε
                bad = [x.strip() for x in m.group(1).split(",")]
                state.setdefault("bad_books", [])
                state["bad_books"] = sorted(set(state["bad_books"]) | set(bad))
                log.warning("Άγνωστοι bookmakers για επιβεβαίωση: %s", bad)
            else:
                log.info("Επιβεβαίωση %s: %s", fid, str(e)[:150])
        except Exception as e:
            log.info("Επιβεβαίωση %s: %s", fid, str(e)[:150])
    if C.BETFAIR_CONFIRM:
        outs = []
        for sg in sigs:
            if sg["outcome"] not in outs:
                outs.append(sg["outcome"])
        for oid in outs[:3]:
            try:
                merge_betfair(hist, api_get("historical-odds", fixtureId=fid,
                                            bookmakers=BETFAIR, outcomeId=oid))
            except QuotaExceeded:
                raise
            except Exception as e:
                log.info("Betfair %s/%s: %s", fid, oid, str(e)[:120])
    return [b for b in sharp_sources() if b in hist]


def has_all_books(hist: dict, markets: dict) -> bool:
    """True αν ο αγώνας έχει αποδόσεις στις αγορές μας σε Pinnacle και σε όλους τους ελληνικούς."""
    for b in [C.SHARP_BOOK] + C.GREEK_BOOKS:
        bm = (hist.get(b) or {}).get("markets") or {}
        if not any(m in bm for m in markets):
            return False
    return True


# ------------------------------------------------------------ Ανάλυση ---------
def series(hist: dict, book: str, market: str, outcome: str) -> list[dict]:
    try:
        rows = hist[book]["markets"][market]["outcomes"][outcome]["players"]["0"]
    except (KeyError, TypeError):
        return []
    pts = []
    for r in rows or []:
        if r.get("price") and r.get("createdAt"):
            pts.append({"t": parse_ts(r["createdAt"]), "price": float(r["price"]),
                        "active": bool(r.get("active", True)), "meta": r.get("exchangeMeta"),
                        "limit": r.get("limit")})
    pts.sort(key=lambda p: p["t"])
    return pts


def current(pts: list[dict], now: dt.datetime | None = None, max_age_min: float | None = None):
    if not pts or not pts[-1]["active"]:
        return None
    if now and max_age_min is not None and now - pts[-1]["t"] > dt.timedelta(minutes=max_age_min):
        return None
    return pts[-1]


def price_at(pts: list[dict], t: dt.datetime) -> dict | None:
    best = None
    for p in pts:
        if p["t"] <= t:
            best = p
        else:
            break
    return best


def fair_odds(hist, market, outcome, outcomes, now=None, max_age=None):
    """Δίκαιη απόδοση: Pinnacle χωρίς γκανιότα (de-vig). Αν λείπει, η απόδοση του Betfair."""
    many = len(outcomes) > 4  # π.χ. ακριβές σκορ: το Pinnacle δεν έχει πάντα όλα τα σκορ
    prices = {}
    for o in outcomes:
        cur = current(series(hist, C.SHARP_BOOK, market, o), now, max_age)
        if cur:
            prices[o] = cur["price"]
        elif not many:
            prices = None
            break
    if prices and outcome in prices and (not many or len(prices) >= 8):
        total = sum(1 / p for p in prices.values())
        if 0.97 < total < (1.45 if many else 1.25):  # λογικό περιθώριο → σχεδόν πλήρης αγορά
            return round(prices[outcome] * total, 3), "Pinnacle"
    if BETFAIR in hist:
        bf = current(series(hist, BETFAIR, market, outcome), now, max_age)
        if bf:
            return bf["price"], "Betfair"
    return None, None


def pct_drop(old: float, new: float) -> float:
    return (old - new) / old * 100 if old else 0.0


DIAG: dict[str, set] = {}   # διαγνωστικά γύρου: τι βρέθηκε / τι κόπηκε και γιατί


def _diag(cat: str, key: str) -> None:
    DIAG.setdefault(cat, set()).add(key)


def thresholds(mk: dict) -> tuple[float, float, float, float, float]:
    """(πτώση 60′, πτώση από αρχή, επιβεβαίωση 60′, επιβεβαίωση από αρχή, ελάχιστο όριο Pinnacle).
    Στις αγορές γκολ οι αποδόσεις κινούνται λιγότερο (το Pinnacle μετακινεί τη γραμμή) → χαμηλότερα όρια."""
    if mk.get("kind") == "totals":
        return (C.TOTALS_DROP_PCT, C.TOTALS_DROP_FROM_OPEN_PCT, C.TOTALS_CONFIRM_DROP_PCT,
                C.TOTALS_CONFIRM_DROP_FROM_OPEN_PCT, C.TOTALS_MIN_PINNACLE_LIMIT)
    return (C.DROP_PCT, C.DROP_FROM_OPEN_PCT, C.CONFIRM_DROP_PCT,
            C.CONFIRM_DROP_FROM_OPEN_PCT, C.MIN_PINNACLE_LIMIT)


def analyze(fx: dict, hist: dict, now: dt.datetime, markets: dict) -> list[dict]:
    live = is_live(fx, now)
    max_age = C.LIVE_MAX_PRICE_AGE_MIN if live else None
    edge_min = C.LIVE_VALUE_EDGE_PCT if live else C.VALUE_EDGE_PCT
    check_drops = (not live) or C.LIVE_DROPS
    minute = int((now - parse_ts(fx["startTime"])).total_seconds() // 60) if live else None
    signals = []
    sharp_books = [b for b in sharp_sources() if b in hist]
    for m, mk in markets.items():
        hi = mk.get("max_odds", C.MAX_ODDS)
        t_drop, t_open, t_cdrop, t_copen, t_lim = thresholds(mk)
        kind = "goals" if mk.get("kind") == "totals" else "1x2"
        for o, label in mk["outcomes"].items():
            dkey = f"{fx['fixtureId']}|{m}|{o}|{kind}"
            big_move = False
            drops = []
            checked = []
            if check_drops:
                for b in sharp_books:
                    pts = series(hist, b, m, o)
                    cur = current(pts, now, max_age)
                    if not cur or not (C.MIN_ODDS * 0.9 <= cur["price"] <= hi * 1.2):
                        continue
                    checked.append(b)
                    past = price_at(pts, now - dt.timedelta(minutes=C.DROP_WINDOW_MIN)) or pts[0]
                    opening = pts[0]
                    d_win = pct_drop(past["price"], cur["price"])
                    d_open = pct_drop(opening["price"], cur["price"])
                    strong = d_win >= t_drop or d_open >= t_open
                    lim = cur.get("limit")
                    if strong and b == C.SHARP_BOOK and lim is not None and lim < t_lim:
                        strong = False  # μικρή αγορά: λίγα λεφτά αρκούν για να κινηθεί → μόνο επιβεβαίωση
                        _diag("small_market", dkey)
                        big_move = True
                    if strong:
                        _diag("drop", dkey)
                        big_move = True
                    if strong or d_win >= t_cdrop or d_open >= t_copen:
                        drops.append({"book": b, "now": cur["price"], "past": past["price"],
                                      "open": opening["price"], "d_win": d_win, "d_open": d_open,
                                      "meta": cur["meta"], "strong": strong, "limit": lim})
            fair, fair_src = fair_odds(hist, m, o, mk["outcomes"], now, max_age)
            greek = []
            for b in C.GREEK_BOOKS:
                cur = current(series(hist, b, m, o), now, max_age)
                if cur:
                    edge = (cur["price"] / fair - 1) * 100 if fair else None
                    greek.append({"book": b, "price": cur["price"], "edge": edge})
            values = [g for g in greek if g["edge"] is not None and g["edge"] >= edge_min
                      and C.MIN_ODDS <= g["price"] <= hi]
            if big_move and not live:
                edges = [g["edge"] for g in greek if g["edge"] is not None]
                e = max(edges) if edges else None
                bucket = ("none" if e is None else "e5" if e >= 5 else "e2" if e >= 2.5
                          else "e0" if e >= 0 else "neg")
                _diag("drop_edge_" + bucket, dkey)
            if values:
                _diag("value", dkey)
            elif any(g["edge"] is not None and g["edge"] >= edge_min and g["price"] > hi for g in greek):
                _diag("odds_high", dkey)
            steam = None
            if (C.STEAM_ALERTS and not values and not live and fair
                    and any(d["strong"] for d in drops)):
                ok = [g for g in greek if g["edge"] is not None and g["edge"] >= C.STEAM_MIN_EDGE_PCT
                      and C.MIN_ODDS <= g["price"] <= hi]
                if ok:
                    steam = max(ok, key=lambda g: g["price"])
            if values or steam or (any(d["strong"] for d in drops) and C.SEND_DROPS_WITHOUT_VALUE):
                signals.append({"fixture": fx, "market": m, "outcome": o, "label": label,
                                "live": live, "minute": minute, "drops": drops, "values": values, "greek": greek,
                                "checked": checked, "steam": steam,
                                "fair": fair, "fair_src": fair_src, "mk": mk})
    return signals


def should_alert(state: dict, sig: dict) -> bool:
    phase = "live" if sig["live"] else "pre"
    key = f"{sig['fixture']['fixtureId']}|{sig['market']}|{sig['outcome']}|{phase}"
    drop = max([max(d["d_win"], d["d_open"]) for d in sig["drops"]], default=0.0)
    edge = max([v["edge"] for v in sig["values"]], default=0.0)
    alerts = state.setdefault("alerts", {})
    prev = alerts.get(key)
    st = stars(sig)
    fire = (prev is None
            or st > prev.get("stars", 0)
            or drop >= prev["drop"] + C.REALERT_DROP_STEP
            or edge >= prev["edge"] + C.REALERT_EDGE_STEP
            or (edge > 0 and prev["edge"] <= 0)
            or (drop > 0 and prev["drop"] <= 0))
    if fire:
        alerts[key] = {
            "drop": round(max(drop, prev["drop"] if prev else 0), 2),
            "edge": round(max(edge, prev["edge"] if prev else 0), 2),
            "start": sig["fixture"]["startTime"],
            "stars": max(st, prev.get("stars", 0) if prev else 0),
        }
    return fire


def in_quiet_hours(now: dt.datetime) -> bool:
    h = now.astimezone(ATHENS).hour
    if C.QUIET_START == C.QUIET_END:
        return False
    if C.QUIET_START < C.QUIET_END:
        return C.QUIET_START <= h < C.QUIET_END
    return h >= C.QUIET_START or h < C.QUIET_END  # π.χ. 23 → 07


def is_serious(sig: dict) -> bool:
    """Ήσυχες ώρες: μόνο τα ⭐⭐⭐."""
    return stars(sig) >= 3


def stars(sig: dict) -> int:
    """⭐ = μόνο αξία στη Stoiximan
    ⭐⭐ = αξία + μεγάλη πτώση σε 1 έξυπνη πηγή (Pinnacle/Betfair/SBOBet/Singbet)
    ⭐⭐⭐ = αξία + μεγάλη πτώση που επιβεβαιώνεται από 2+ πηγές"""
    if not sig["values"] and not sig.get("steam"):
        return 0
    if not any(d.get("strong", True) for d in sig["drops"]):
        return 1
    return 3 if len({d["book"] for d in sig["drops"]}) >= 2 else 2


def confirmed(sig: dict) -> bool:
    """Η πτώση φαίνεται σε 2+ έξυπνες πηγές → σίγουρα μπαίνουν μεγάλα λεφτά."""
    return stars(sig) >= 3


# ------------------------------------------------------------ Μηνύματα ---------
FLAGS = {  # χώρα (όπως τη γράφει το API) → (σημαία, ελληνικό όνομα)
    "england": ("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Αγγλία"), "scotland": ("🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Σκωτία"), "wales": ("🏴󠁧󠁢󠁷󠁬󠁳󠁿", "Ουαλία"),
    "spain": ("🇪🇸", "Ισπανία"), "italy": ("🇮🇹", "Ιταλία"), "germany": ("🇩🇪", "Γερμανία"),
    "france": ("🇫🇷", "Γαλλία"), "greece": ("🇬🇷", "Ελλάδα"), "netherlands": ("🇳🇱", "Ολλανδία"),
    "portugal": ("🇵🇹", "Πορτογαλία"), "turkey": ("🇹🇷", "Τουρκία"), "turkiye": ("🇹🇷", "Τουρκία"),
    "belgium": ("🇧🇪", "Βέλγιο"), "switzerland": ("🇨🇭", "Ελβετία"), "denmark": ("🇩🇰", "Δανία"),
    "austria": ("🇦🇹", "Αυστρία"), "norway": ("🇳🇴", "Νορβηγία"), "sweden": ("🇸🇪", "Σουηδία"),
    "poland": ("🇵🇱", "Πολωνία"), "czechia": ("🇨🇿", "Τσεχία"), "czech republic": ("🇨🇿", "Τσεχία"),
    "croatia": ("🇭🇷", "Κροατία"), "romania": ("🇷🇴", "Ρουμανία"), "serbia": ("🇷🇸", "Σερβία"),
    "cyprus": ("🇨🇾", "Κύπρος"), "saudi arabia": ("🇸🇦", "Σαουδική Αραβία"), "usa": ("🇺🇸", "ΗΠΑ"),
    "brazil": ("🇧🇷", "Βραζιλία"), "argentina": ("🇦🇷", "Αργεντινή"),
    "international clubs": ("🇪🇺", "Ευρώπη"), "europe": ("🇪🇺", "Ευρώπη"),
}


def country_flag(f: dict) -> tuple[str, str]:
    for key in (norm(f.get("categoryName")), norm(f.get("categorySlug"))):
        if key in FLAGS:
            return FLAGS[key]
    if any(re.search(p, norm(f.get("tournamentName"))) for p in C.CUPS):
        return "🇪🇺", "Ευρώπη"
    return "🌍", f.get("categoryName") or ""


def name(b: str) -> str:
    return C.BOOK_NAMES.get(b, b)


def meta_text(meta) -> str:
    if not isinstance(meta, dict):
        return ""
    keys = ("vol", "matched", "liquid", "traded", "size")
    parts = [f"{k}: {v}" for k, v in meta.items()
             if any(x in k.lower() for x in keys) and v not in (None, "", 0)]
    return f" <i>({html.escape(', '.join(parts))})</i>" if parts else ""


def pick_text(sig: dict, home: str, away: str) -> str:
    mk, label = sig["mk"], sig["label"]
    if mk["kind"] == "1x2":
        lab = {"1": "1", "x": "Χ", "2": "2"}.get(norm(label), label)
        team = {"1": home, "2": away}.get(lab)
        return lab + (f" ({team})" if team else "")
    if mk["kind"] == "totals":
        try:
            line = f" {float(mk['line']):g}"
        except (TypeError, ValueError):
            line = ""
        return {"over": "Over", "under": "Under"}.get(norm(label), label) + line
    return label


def format_signal(sig: dict) -> str:
    f = sig["fixture"]
    h = f.get("participant1ShortName") or f.get("participant1Name") or "?"
    a = f.get("participant2ShortName") or f.get("participant2Name") or "?"
    flag, country = country_flag(f)
    start = parse_ts(f["startTime"]).astimezone(ATHENS)
    if sig["live"]:
        when = f"🔴 LIVE (~{max(sig.get('minute') or 0, 0)}′ από την έναρξη)"
    else:
        when = f"🕒 {GR_DAYS[start.weekday()]} {start:%d/%m %H:%M}"

    st = stars(sig)
    n_src = len({d["book"] for d in sig["drops"]})
    steam = sig.get("steam") if not sig["values"] else None
    if steam:
        head = f"📢 ΜΠΑΙΝΟΥΝ ΜΕΓΑΛΑ ΛΕΦΤΑ ({n_src} {'πηγές' if n_src > 1 else 'πηγή'})"
    elif st >= 3:
        head = f"🔥🔥 ΑΞΙΖΕΙ · ΜΕΓΑΛΑ ΛΕΦΤΑ ({n_src} πηγές)"
    elif st == 2:
        head = "🔥 ΑΞΙΖΕΙ · ΜΠΑΙΝΟΥΝ ΛΕΦΤΑ"
    elif sig["values"]:
        head = "💰 ΑΞΙΖΕΙ"
    else:
        head = "📉 ΜΕΓΑΛΗ ΠΤΩΣΗ (χωρίς αξία στη Stoiximan)"
    if sig.get("quiet"):
        head = "🚨 " + head
    lines = [f"<b>{head}</b>  {'⭐' * max(st, 1)}",
             f"{flag} <b>{html.escape(h)} – {html.escape(a)}</b>",
             f"🏆 {html.escape(country)} · {html.escape(f.get('tournamentName') or '')}",
             when,
             f"🎯 {html.escape(sig['mk']['name'])}: <b>{html.escape(pick_text(sig, h, a))}</b>", ""]
    for v in sig["values"]:
        lines.append(f"✅ <b>{name(v['book'])}: {v['price']:.2f}</b> → "
                     f"<b>{v['edge']:+.1f}%</b> σε σχέση με τη δίκαιη ({sig['fair']:.2f})")
    if steam:
        lines.append(f"🔵 <b>{name(steam['book'])}: {steam['price']:.2f}</b> → {steam['edge']:+.1f}% σε σχέση "
                     f"με τη δίκαιη ({sig['fair']:.2f}) · έχει ήδη προσαρμοστεί, χωρίς έξτρα αξία")
    if sig.get("stake"):
        lines.append(f"💰 Προτεινόμενο ποντάρισμα: <b>{sig['stake']:g}€</b> "
                     f"(κάσα {sig.get('bank', C.BANKROLL):g}€)")
    if sig["fair"]:
        prob = 100 / sig["fair"]
        lvl = "🟢" if prob >= 50 else ("🟡" if prob >= 40 else "🔴")
        lines.append(f"📊 Πιθανότητα να βγει ≈ <b>{prob:.0f}%</b> {lvl}")
    for d in sorted(sig["drops"], key=lambda d: not d.get("strong", True)):
        lines.append(f"💸 {name(d['book'])}: {d['past']:.2f} → <b>{d['now']:.2f}</b> "
                     f"(−{d['d_win']:.0f}% σε {C.DROP_WINDOW_MIN}′, −{d['d_open']:.0f}% από αρχή "
                     f"{d['open']:.2f}){meta_text(d['meta'])}")
    pin = next((d for d in sig["drops"] if d["book"] == C.SHARP_BOOK and d.get("limit")), None)
    if pin:
        lim = pin["limit"]
        tag = "🟢 μεγάλη αγορά" if lim >= 3 * C.MIN_PINNACLE_LIMIT else (
            "🟡" if lim >= C.MIN_PINNACLE_LIMIT else "🔴 μικρή αγορά")
        lines.append(f"💶 Το Pinnacle δέχεται έως €{lim:,.0f} εδώ {tag}".replace(",", "."))
    checked = sig.get("checked") or []
    if checked and not sig["live"]:
        dropped = {d["book"] for d in sig["drops"]}
        marks = " · ".join(f"{name(b)} {'✅' if b in dropped else '▫️'}" for b in checked)
        lines.append(f"🔎 Πηγές: {marks}")
    if st >= 3:
        lines.append(f"💪 Η πτώση επιβεβαιώνεται από {n_src} ανεξάρτητες πηγές — μπαίνουν μεγάλα λεφτά.")
    if steam:
        lines.append("👉 Ακολουθείς τα έξυπνα λεφτά. Μικρότερο ποντάρισμα — μετράμε χωριστά αν αξίζουν.")
    elif st >= 2:
        lines.append("👉 Οι επαγγελματίες ποντάρουν εδώ και η Stoiximan δεν έχει ρίξει ακόμα την απόδοση.")
    elif sig["values"]:
        lines.append("👉 Η Stoiximan δίνει πάνω από την πραγματική πιθανότητα.")
    lines.append("<i>⏱ Έλεγξε την απόδοση πριν παίξεις — μπορεί να αλλάξει γρήγορα.</i>")
    lines.append("<i>✍️ Αν το παίξεις, απάντησε με το ποσό (π.χ. 10). Χωρίς απάντηση = δεν παίχτηκε.</i>")
    return "\n".join(lines)


def send_telegram(text: str, reply_to: int | None = None) -> int | None:
    body = {"chat_id": C.TELEGRAM_CHAT_ID, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_to:
        body["reply_to_message_id"] = reply_to
    r = requests.post(f"https://api.telegram.org/bot{C.TELEGRAM_TOKEN}/sendMessage", json=body, timeout=20)
    if r.status_code != 200:
        log.error("Telegram σφάλμα %s: %s", r.status_code, r.text)
    r.raise_for_status()
    try:
        return r.json()["result"]["message_id"]
    except Exception:
        return None


# ---------------------------------------------------------- Δελτία ημέρας ---------
TICKET_GROUP_NAMES = {"1x2": "1Χ2", "goals": "Γκολ", "btts": "Goal/No Goal", "corners": "Κόρνερ", "cards": "Κάρτες"}


def ticket_group(mid: str, m: dict, markets: dict) -> str | None:
    """Σε ποια κατηγορία ανήκει μια αγορά (για τα δελτία). None = δεν τη χρησιμοποιούμε."""
    name = norm(m.get("marketName"))
    try:
        line = float(m.get("handicap") or 0)
    except (TypeError, ValueError):
        line = 0.0
    if mid == "101":
        return "1x2"
    if mid in markets and markets[mid]["kind"] == "totals":
        return "goals"
    if name == "over under full time" and line in (1.5, 2.5, 3.5):
        return "goals"
    if name == "both teams to score":
        return "btts"
    if name.startswith("corners over under full time") and line % 1 == 0.5:
        return "corners"
    if name.startswith("bookings over under full time") and line % 1 == 0.5:
        return "cards"
    return None


def ticket_label(group: str, m: dict, oname: str, fx: dict, mk_name: str) -> str:
    on = norm(oname)
    try:
        line = f"{float(m.get('handicap')):g}"
    except (TypeError, ValueError):
        line = ""
    ou = {"over": "Over", "under": "Under"}.get(on, oname)
    if group == "1x2":
        h = fx.get("participant1ShortName") or fx.get("participant1Name") or ""
        a = fx.get("participant2ShortName") or fx.get("participant2Name") or ""
        return {"1": f"1 ({h})", "x": "Χ", "2": f"2 ({a})"}.get(on, oname)
    if group == "goals":
        pre = "Ημίχρονο " if "μιχρ" in mk_name or norm(m.get("period")) in ("p1", "1sthalf", "first half") else ""
        return f"{pre}{ou} {line} γκολ"
    if group == "btts":
        return "Goal/Goal: " + {"yes": "Ναι", "no": "Όχι"}.get(on, oname)
    if group == "corners":
        return f"Κόρνερ {ou} {line}"
    if group == "cards":
        return f"Κάρτες {ou} {line}"
    return oname


def collect_candidates(state: dict, fx: dict, hist: dict, now: dt.datetime, cat: dict, markets: dict) -> int:
    """Από τα δεδομένα που ήδη κατεβάσαμε (χωρίς έξτρα αιτήματα): οι καλύτερες επιλογές του αγώνα
    για τα δελτία = όσο πιο κοντά/πάνω από τη δίκαιη απόδοση η Stoiximan + αν μπαίνουν λεφτά."""
    pin = (hist.get(C.SHARP_BOOK) or {}).get("markets") or {}
    out = []
    flag, _country = country_flag(fx)
    h = fx.get("participant1ShortName") or fx.get("participant1Name") or "?"
    a = fx.get("participant2ShortName") or fx.get("participant2Name") or "?"
    for mid in pin:
        m = cat.get(str(mid))
        if not m:
            continue
        group = ticket_group(str(mid), m, markets)
        if not group:
            continue
        outs = {str(o.get("outcomeId")): str(o.get("outcomeName") or "") for o in (m.get("outcomes") or [])}
        if len(outs) < 2:
            continue
        mk_name = markets.get(str(mid), {}).get("name", "")
        for o, oname in outs.items():
            fair, src = fair_odds(hist, str(mid), o, outs, None, None)
            if not fair or src != "Pinnacle":
                continue
            best = None
            for b in C.GREEK_BOOKS:
                cur = current(series(hist, b, str(mid), o))
                if cur and (best is None or cur["price"] > best["price"]):
                    best = {"book": b, "price": cur["price"]}
            if not best or not (C.TICKET_LEG_MIN_ODDS <= best["price"] <= C.TICKET_LEG_MAX_ODDS):
                continue
            edge = (best["price"] / fair - 1) * 100
            if edge < C.TICKET_MIN_EDGE_PCT:
                continue
            pts = series(hist, C.SHARP_BOOK, str(mid), o)
            drop = pct_drop(pts[0]["price"], pts[-1]["price"]) if len(pts) > 1 else 0.0
            score = edge + C.TICKET_DROP_WEIGHT * min(max(drop, 0.0), 20.0)
            out.append({"fid": fx["fixtureId"], "start": fx["startTime"], "match": f"{flag} {h} – {a}",
                        "group": group, "market": str(mid), "outcome": o,
                        "label": ticket_label(group, m, oname, fx, mk_name),
                        "book": best["book"], "price": round(best["price"], 3), "fair": fair,
                        "edge": round(edge, 1), "drop": round(drop, 1), "prob": round(1 / fair, 4),
                        "score": round(score, 2)})
    out.sort(key=lambda c: -c["score"])
    keep, seen = [], set()
    for c in out:  # έως 6 ανά αγώνα, το πολύ 2 από την ίδια κατηγορία
        if sum(1 for k in keep if k["group"] == c["group"]) >= 2 or (c["market"], c["outcome"]) in seen:
            continue
        keep.append(c)
        seen.add((c["market"], c["outcome"]))
        if len(keep) >= 6:
            break
    cands = state.setdefault("cands", {})
    if keep:
        cands[fx["fixtureId"]] = keep
    else:
        cands.pop(fx["fixtureId"], None)
    return len(keep)


def build_ticket(pool: list[dict], spec: dict, avoid: set) -> list[dict] | None:
    """Αναζήτηση (beam search) στις καλύτερες επιλογές: ένα σημείο ανά αγώνα, συνολική απόδοση μέσα
    στο [min, max], με το μεγαλύτερο άθροισμα "ποιότητας" (αξία + μπαίνουν λεφτά)."""
    lo = spec.get("min", spec["target"] * 0.8)
    hi = spec.get("max", spec["target"] * 1.5)
    groups = set(spec.get("groups") or TICKET_GROUP_NAMES)
    for allow_reuse in (False, True):
        cands = [c for c in pool if c["group"] in groups
                 and (allow_reuse or (c["fid"], c["market"], c["outcome"]) not in avoid)][:C.TICKET_POOL_SIZE]
        beam = [((), 1.0, 0.0, frozenset())]   # (δείκτες, απόδοση, βαθμός, αγώνες)
        best = None
        for _depth in range(C.TICKET_MAX_LEGS):
            nxt = []
            for idx, odds, score, fids in beam:
                start = idx[-1] + 1 if idx else 0
                for j in range(start, len(cands)):
                    c = cands[j]
                    if c["fid"] in fids:
                        continue
                    o2 = odds * c["price"]
                    if o2 > hi:
                        continue
                    st = (idx + (j,), o2, score + c["score"], fids | {c["fid"]})
                    if o2 >= lo:
                        # προτιμάμε υψηλότερο μέσο βαθμό και λιγότερα σημεία (λιγότερο ρίσκο)
                        key = (st[2] / len(st[0]), -len(st[0]))
                        if best is None or key > best[0]:
                            best = (key, st)
                    else:
                        nxt.append(st)
            nxt.sort(key=lambda st: -(st[2] / len(st[0])))
            beam = nxt[: C.TICKET_BEAM]
            if not beam:
                break
        if best:
            return [cands[j] for j in best[1][0]]
    return None


def format_ticket(spec: dict, legs: list[dict], test: bool = False) -> str:
    odds = 1.0
    prob = 1.0
    for c in legs:
        odds *= c["price"]
        prob *= c["prob"]
    lines = [f"{'🧪 ' if test else ''}🎟️ <b>{html.escape(spec['name'])}</b> · απόδοση <b>{odds:.2f}</b>", ""]
    for i, c in enumerate(sorted(legs, key=lambda c: c["start"]), 1):
        t = parse_ts(c["start"]).astimezone(ATHENS)
        money = " 💸" if c["drop"] >= C.TICKET_MONEY_DROP_PCT else ""
        lines.append(f"{i}. {html.escape(c['match'])} · {t:%H:%M}\n"
                     f"     ➜ <b>{html.escape(c['label'])}</b> @{c['price']:.2f}{money}")
    lines += ["", f"📊 Πιθανότητα να βγει ≈ <b>{prob * 100:.1f}%</b> (περίπου 1 στις {max(1, round(1 / prob))})",
              "💸 = μπαίνουν λεφτά σε αυτή την επιλογή (πτώση στο Pinnacle)",
              "<i>Απάντησε με το ποσό που έπαιξες (π.χ. 5) και, όταν κριθεί, με ✅ ή ❌.</i>"]
    return "\n".join(lines)


def maybe_send_tickets(state: dict, now: dt.datetime, force: bool = False, test: bool = False) -> int:
    """Μία φορά τη μέρα (TICKETS_TIME): στέλνει τα δελτία της ημέρας."""
    if not C.TICKETS_ENABLED:
        return 0
    d = now.astimezone(ATHENS)
    today = d.strftime("%Y-%m-%d")
    hh, mm = (int(x) for x in C.TICKETS_TIME.split(":"))
    if not force and (state.get("tickets_sent") == today or (d.hour, d.minute) < (hh, mm)):
        return 0
    earliest = now + dt.timedelta(minutes=C.TICKET_MIN_MINUTES_BEFORE)
    latest = now + dt.timedelta(hours=C.TICKET_WINDOW_HOURS)
    pool = [c for lst in state.get("cands", {}).values() for c in lst
            if earliest <= parse_ts(c["start"]) <= latest]
    pool.sort(key=lambda c: -c["score"])
    sent, avoid = 0, set()
    header = (f"{'🧪 ' if test else ''}🎟️ <b>ΔΕΛΤΙΑ ΗΜΕΡΑΣ · {GR_DAYS[d.weekday()]} {d:%d/%m}</b>\n"
              f"<i>Από {len({c['fid'] for c in pool})} αγώνες έως τις {latest.astimezone(ATHENS):%H:%M}, "
              "οι επιλογές όπου η Stoiximan είναι κοντά ή πάνω από τη δίκαιη απόδοση και μπαίνουν λεφτά. "
              "Όσο μεγαλύτερη η απόδοση, τόσο μεγαλύτερο το ρίσκο — μικρά ποσά.</i>")
    try:
        send_telegram(header)
    except Exception as e:
        log.warning("Δελτία: %s", e)
        return 0
    tickets = state.setdefault("tickets", {})
    for i, spec in enumerate(C.TICKETS):
        legs = build_ticket(pool, spec, avoid)
        if not legs:
            try:
                send_telegram(f"🎟️ <b>{html.escape(spec['name'])}</b>: δεν βρέθηκαν αρκετές καλές επιλογές σήμερα.")
            except Exception:
                pass
            continue
        avoid |= {(c["fid"], c["market"], c["outcome"]) for c in legs}
        try:
            mid = send_telegram(format_ticket(spec, legs, test))
        except Exception as e:
            log.warning("Δελτίο: %s", e)
            continue
        sent += 1
        if test:
            continue
        odds = 1.0
        prob = 1.0
        for c in legs:
            odds *= c["price"]
            prob *= c["prob"]
        tickets[f"{today}|{i}"] = {"date": today, "name": spec["name"], "odds": round(odds, 2),
                                   "prob": round(prob, 5), "msg_ids": [mid] if mid else [],
                                   "legs": [f"{c['match']} · {c['label']} @{c['price']:.2f}" for c in legs],
                                   "last_start": max(c["start"] for c in legs), "stake": None, "result": None}
    if not force:
        state["tickets_sent"] = today
    return sent


def ticket_pnl(t: dict) -> float:
    st = t.get("stake") or 0
    if t.get("result") == "WIN":
        return round(st * (t["odds"] - 1), 2)
    if t.get("result") == "LOSE":
        return round(-st, 2)
    return 0.0


# ---------------------------------------------------- Στατιστικά / PnL ---------
SETTLE_PNL = {"WIN": 1.0, "HALFWIN": 0.5, "PUSH": 0.0, "CANCELLED": 0.0,
              "HALFLOSS": -0.5, "LOSE": -1.0}


def record_bet(state: dict, sig: dict, msg_id: int | None = None) -> None:
    """Κάθε ειδοποίηση = στοίχημα STAKE € (αλλάζει με απάντηση στο Telegram) στην απόδοση της Stoiximan."""
    f = sig["fixture"]
    key = f"{f['fixtureId']}|{sig['market']}|{sig['outcome']}"
    bets = state.setdefault("bets", {})
    if key in bets or not (sig["values"] or sig.get("steam")):
        if key in bets:  # αναβάθμιση αστεριών → κρατάμε το καλύτερο
            bets[key]["stars"] = max(bets[key].get("stars", 0), stars(sig))
            if msg_id:
                bets[key].setdefault("msg_ids", []).append(msg_id)
        return
    v = max(sig["values"], key=lambda x: x["price"]) if sig["values"] else sig["steam"]
    h = f.get("participant1ShortName") or f.get("participant1Name") or "?"
    a = f.get("participant2ShortName") or f.get("participant2Name") or "?"
    pin = next((d for d in sig["drops"] if d["book"] == C.SHARP_BOOK), None)
    bets[key] = {
        "fixtureId": f["fixtureId"], "market": sig["market"], "outcome": sig["outcome"],
        "match": f"{country_flag(f)[0]} {h} – {a}",
        "pick": f"{sig['mk']['name']}: {pick_text(sig, h, a)}",
        "book": v["book"], "price": round(v["price"], 3), "edge": round(v["edge"], 1),
        "fair": sig["fair"], "stars": stars(sig), "start": f["startTime"],
        "kind": "value" if sig["values"] else "steam",
        "pin_limit": pin.get("limit") if pin else None,
        "sent_at": iso(dt.datetime.now(dt.timezone.utc)),
        "status": "open", "tries": 0,
        "stake": 0.0, "suggested": sig.get("stake", C.STAKE), "replied": False,  # 0 μέχρι να απαντήσεις
        "msg_ids": [msg_id] if msg_id else [],
    }


def bankroll(state: dict) -> float:
    """Τρέχουσα κάσα = αρχική + κέρδη/ζημιές των κλεισμένων στοιχημάτων."""
    return round(C.BANKROLL + sum(bet_pnl(b) for b in state.get("bets", {}).values())
                 + sum(ticket_pnl(t) for t in state.get("tickets", {}).values()), 2)


def suggest_stake(sig: dict, state: dict) -> float:
    """Kelly: f = (p·απόδοση − 1) / (απόδοση − 1), με p = 1/δίκαιη απόδοση.
    Ποντάρισμα = κάσα × f × KELLY_FRACTION, με όριο MAX_STAKE_PCT% και ελάχιστο MIN_STAKE."""
    if not sig.get("values") or not sig.get("fair"):
        return C.STAKE
    price = max(v["price"] for v in sig["values"])
    p = 1 / sig["fair"]
    f = (p * price - 1) / (price - 1) if price > 1 else 0
    bank = max(bankroll(state), 0)
    stake = bank * max(f, 0) * C.KELLY_FRACTION
    stake = min(stake, bank * C.MAX_STAKE_PCT / 100)
    stake = round(stake * 2) / 2  # στρογγύλεμα στα 0,50€
    return max(C.MIN_STAKE, stake) if bank >= C.MIN_STAKE else 0.0


def steam_stake(state: dict) -> float:
    """📢 ειδοποιήσεις (χωρίς έξτρα αξία): μικρό σταθερό ποσό, STEAM_STAKE_PCT% της κάσας."""
    bank = max(bankroll(state), 0)
    return max(C.MIN_STAKE, round(bank * C.STEAM_STAKE_PCT / 100 * 2) / 2) if bank >= C.MIN_STAKE else 0.0


def bet_pnl(b: dict) -> float:
    if b.get("status") != "settled":
        return 0.0
    stake = b.get("stake", C.STAKE)
    mult = SETTLE_PNL.get(b.get("result"), 0.0)
    return round(stake * (b["price"] - 1) * mult if mult > 0 else stake * mult, 2)


# ---- Ποντάρισμα από Telegram: απάντηση σε ειδοποίηση με ένα ποσό ----
def process_replies(state: dict) -> int:
    """Διαβάζει απαντήσεις στο Telegram. Απάντηση σε ειδοποίηση με αριθμό (π.χ. 25 ή 0)
    = πόσα € έπαιξες σε αυτό το ματς (0 = δεν το έπαιξα, δεν μετράει στο PnL)."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{C.TELEGRAM_TOKEN}/getUpdates", timeout=20,
                         params={"offset": state.get("tg_offset", 0), "timeout": 0,
                                 "allowed_updates": json.dumps(["message"])})
        updates = r.json().get("result", []) if r.ok else []
    except Exception as e:
        log.info("Telegram replies: %s", e)
        return 0
    by_msg = {mid: k for k, b in state.get("bets", {}).items() for mid in b.get("msg_ids", [])}
    by_ticket = {mid: k for k, t in state.get("tickets", {}).items() for mid in t.get("msg_ids", [])}
    changed = 0
    for u in updates:
        state["tg_offset"] = u["update_id"] + 1
        m = u.get("message") or {}
        if str((m.get("chat") or {}).get("id")) != str(C.TELEGRAM_CHAT_ID):
            continue
        rep_id = (m.get("reply_to_message") or {}).get("message_id")
        txt = (m.get("text") or "").strip().replace("€", "").replace(",", ".")
        if rep_id in by_ticket:
            t = state["tickets"][by_ticket[rep_id]]
            low = norm(txt)
            if txt.startswith("✅") or low in ("win", "κερδισε", "κερδισα", "μπηκε", "βγηκε", "ok"):
                t["result"], note = "WIN", f"✅ Κέρδισε! +{(t.get('stake') or 0) * (t['odds'] - 1):.2f}€"
            elif txt.startswith("❌") or low in ("lose", "εχασε", "εχασα", "καηκε", "χαθηκε"):
                t["result"], note = "LOSE", f"❌ Χάθηκε ({-(t.get('stake') or 0):.2f}€)"
            else:
                try:
                    amount = float(txt)
                except ValueError:
                    continue
                if not 0 <= amount <= 100000:
                    continue
                t["stake"] = amount
                note = f"✅ Ποσό δελτίου: {amount:g}€" if amount else "Το δελτίο δεν παίχτηκε."
            changed += 1
            try:
                send_telegram(f"{note}\n<i>{html.escape(t['name'])} @{t['odds']:.2f}</i>",
                              reply_to=m.get("message_id"))
            except Exception:
                pass
            continue
        if rep_id not in by_msg:
            continue
        try:
            amount = float(txt)
        except ValueError:
            continue
        if not 0 <= amount <= 100000:
            continue
        b = state["bets"][by_msg[rep_id]]
        b["stake"] = amount
        b["replied"] = True
        changed += 1
        note = "❌ Δεν μετράει στο PnL (δεν το έπαιξες)." if amount == 0 else f"✅ Ποντάρισμα: {amount:g}€"
        try:
            send_telegram(f"{note}\n<i>{html.escape(b['match'])} · {html.escape(b['pick'])} @{b['price']:.2f}</i>",
                          reply_to=m.get("message_id"))
        except Exception:
            pass
    return changed


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, key)
            if r is not None:
                return r
    return None


def quota_left() -> int | None:
    """Πόσα χρεώσιμα αιτήματα μένουν αυτόν τον μήνα (το /account δεν χρεώνεται)."""
    try:
        acc = api_get("account")
        lim, cnt = _find(acc, "request_limit"), _find(acc, "request_count")
        return int(lim) - int(cnt) if lim is not None and cnt is not None else None
    except Exception as e:
        log.info("Έλεγχος ορίου: %s", e)
        return None


# ---- CLV: πήραμε καλύτερη απόδοση από την τελική (closing) του Pinnacle; ----
def closing_fair(hist: dict, market: str, outcome: str, start: dt.datetime) -> float | None:
    """Δίκαιη απόδοση του Pinnacle τη στιγμή της σέντρας (χωρίς γκανιότα)."""
    try:
        outs = hist[C.SHARP_BOOK]["markets"][market]["outcomes"]
    except (KeyError, TypeError):
        return None
    prices = {}
    for o in outs:
        p = price_at(series(hist, C.SHARP_BOOK, market, o), start)
        if p:
            prices[o] = p["price"]
    if outcome not in prices or len(prices) < len(outs):
        return None
    total = sum(1 / p for p in prices.values())
    if not 0.97 < total < 1.25:
        return None
    return round(prices[outcome] * total, 3)


def compute_clv(state: dict, now: dt.datetime) -> int:
    """Μετά τη σέντρα: συγκρίνει την απόδοση της ειδοποίησης με την τελική του Pinnacle (δωρεάν)."""
    bets = state.get("bets", {})
    todo: dict[str, list[str]] = {}
    for k, b in bets.items():
        if "clv" in b or b.get("clv_tries", 0) >= 3:
            continue
        if now >= parse_ts(b["start"]) + dt.timedelta(minutes=10):
            todo.setdefault(b["fixtureId"], []).append(k)
    done = 0
    for fid, keys in list(todo.items())[: C.CLV_MAX_PER_RUN]:
        try:
            data = api_get("historical-odds", fixtureId=fid, bookmakers=C.SHARP_BOOK)
            hist = dict(data.get("bookmakers") or {})
        except QuotaExceeded:
            break
        except Exception as e:
            log.info("CLV %s: %s", fid, str(e)[:120])
            hist = {}
        done += 1
        for k in keys:
            b = bets[k]
            cf = closing_fair(hist, b["market"], b["outcome"], parse_ts(b["start"]))
            if cf:
                b["close"] = cf
                b["clv"] = round((b["price"] / cf - 1) * 100, 1)
            else:
                b["clv_tries"] = b.get("clv_tries", 0) + 1
    return done


def settle_bets(state: dict, now: dt.datetime) -> int:
    """Βρίσκει τα αποτελέσματα των ανοιχτών στοιχημάτων (1 χρεώσιμο αίτημα ανά αγώνα)."""
    bets = state.get("bets", {})
    due: dict[str, list[str]] = {}
    for k, b in bets.items():
        if b["status"] != "open":
            continue
        wait_h = C.SETTLE_AFTER_HOURS + C.SETTLE_RETRY_HOURS * b.get("tries", 0)  # 3ω, 5ω, 7ω…
        if now >= parse_ts(b["start"]) + dt.timedelta(hours=wait_h):
            due.setdefault(b["fixtureId"], []).append(k)
    if not due:
        return 0
    today = now.astimezone(ATHENS).strftime("%Y-%m-%d")
    used = {d: n for d, n in state.get("settle_used", {}).items() if d >= today}
    state["settle_used"] = used
    budget = C.SETTLE_MAX_PER_DAY - used.get(today, 0)
    if budget <= 0:
        return 0
    left = quota_left()
    if left is not None:
        budget = min(budget, max(0, left - C.QUOTA_RESERVE))
    done = 0
    def order(kv):  # πρώτα όσα παίχτηκαν πραγματικά (ποσό > 0), μετά τα παλιότερα
        played = any(bets[k].get("stake", C.STAKE) > 0 for k in kv[1])
        return (not played, min(bets[k]["start"] for k in kv[1]))
    for fid, keys in sorted(due.items(), key=order):
        if done >= budget:
            break
        try:
            data = api_get("settlements", fixtureId=fid)
        except QuotaExceeded:
            break
        except Exception as e:
            data = None
            log.info("Αποτέλεσμα %s: %s", fid, str(e)[:150])
        used[today] = used.get(today, 0) + 1
        done += 1
        for k in keys:
            b = bets[k]
            try:
                res = data["markets"][b["market"]]["outcomes"][b["outcome"]]["players"]["0"]["result"]
            except (KeyError, TypeError):
                res = None
            if res in SETTLE_PNL:
                b.update(status="settled", result=res, settled_at=iso(now))
                b["pnl"] = bet_pnl(b)
            else:
                b["tries"] = b.get("tries", 0) + 1
                if b["tries"] >= C.SETTLE_MAX_TRIES:
                    b.update(status="unknown", settled_at=iso(now))
    log.info("Αποτελέσματα: έλεγχος %d αγώνων", done)
    return done


def virtual_pnl(b: dict) -> float:
    """Κέρδος/ζημιά αν είχε παιχτεί με το προτεινόμενο ποσό (για να κρίνουμε το σύστημα)."""
    return bet_pnl({**b, "stake": b.get("suggested", b.get("stake", C.STAKE))})


def _virtual_summary(bets: list[dict]) -> str:
    done = [b for b in bets if b.get("status") == "settled"]
    if not done:
        return "—"
    w = sum(1 for b in done if b.get("result") in ("WIN", "HALFWIN"))
    l = sum(1 for b in done if b.get("result") in ("LOSE", "HALFLOSS"))
    pnl = sum(virtual_pnl(b) for b in done)
    staked = sum(b.get("suggested", b.get("stake", C.STAKE)) for b in done)
    roi = pnl / staked * 100 if staked else 0
    return f"{len(done)} στοιχ. · {w}✅ {l}❌ · PnL <b>{pnl:+.2f}€</b> · ROI {roi:+.1f}%"


def _summary(bets: list[dict]) -> str:
    played = [b for b in bets if b.get("stake", C.STAKE) > 0]
    if not played:
        return "—"
    w = sum(1 for b in played if b.get("result") in ("WIN", "HALFWIN"))
    l = sum(1 for b in played if b.get("result") in ("LOSE", "HALFLOSS"))
    pnl = sum(bet_pnl(b) for b in played)
    staked = sum(b.get("stake", C.STAKE) for b in played)
    roi = pnl / staked * 100 if staked else 0
    return f"{len(played)} στοιχ. · {w}✅ {l}❌ · PnL <b>{pnl:+.2f}€</b> · ROI {roi:+.1f}%"


def _clv_summary(bets: list[dict]) -> str | None:
    c = [b["clv"] for b in bets if "clv" in b]
    if not c:
        return None
    beat = sum(1 for x in c if x > 0)
    avg = sum(c) / len(c)
    verdict = "👍 καλό σημάδι" if avg > 0 else "👎 οι αποδόσεις μας δεν είναι καλύτερες από την αγορά"
    return f"🎯 CLV: μέσος όρος <b>{avg:+.1f}%</b> · κερδίσαμε την τελική απόδοση σε {beat}/{len(c)} ({verdict})"


def save_diag(state: dict, now: dt.datetime) -> None:
    """Κρατάει ανά ημέρα (ώρα Ελλάδας) τι βρέθηκε και τι κόπηκε, χωρίς διπλομετρήματα."""
    today = now.astimezone(ATHENS).strftime("%Y-%m-%d")
    diag = {d: v for d, v in state.get("diag", {}).items() if d >= (now - dt.timedelta(days=2))
            .astimezone(ATHENS).strftime("%Y-%m-%d")}
    day = diag.setdefault(today, {})
    for cat, keys in DIAG.items():
        day[cat] = sorted(set(day.get(cat, [])) | keys)
    state["diag"] = diag


def diag_line(state: dict, now: dt.datetime) -> str | None:
    day = state.get("diag", {}).get(now.astimezone(ATHENS).strftime("%Y-%m-%d"))
    if not day:
        return None
    def n(cat, kind=None):
        return sum(1 for k in day.get(cat, []) if kind is None or k.endswith("|" + kind))
    return (f"🔍 <b>Σήμερα:</b> {n('fixtures')} αγώνες · ευκαιρίες αξίας {n('value')} "
            f"(1Χ2 {n('value', '1x2')} · γκολ {n('value', 'goals')}) · μεγάλες πτώσεις {n('drop')} "
            f"(1Χ2 {n('drop', '1x2')} · γκολ {n('drop', 'goals')}) · ειδοποιήσεις {n('alert')}\n"
            f"✂️ Κόπηκαν: {n('odds_high')} λόγω απόδοσης &gt;{C.MAX_ODDS:g} · "
            f"{n('small_market')} λόγω μικρής αγοράς\n"
            f"📐 Στις μεγάλες πτώσεις η Stoiximan έδινε: ≥5%: {n('drop_edge_e5')} · "
            f"2.5–5%: {n('drop_edge_e2')} · 0–2.5%: {n('drop_edge_e0')} · "
            f"κάτω από τη δίκαιη: {n('drop_edge_neg')} · χωρίς απόδοση: {n('drop_edge_none')}")


def report_day(now: dt.datetime) -> dt.date:
    """Ο πρωινός απολογισμός αφορά την προηγούμενη μέρα· μετά τις 15:00 αφορά τη σημερινή."""
    d = now.astimezone(ATHENS)
    return (d - dt.timedelta(days=1)).date() if d.hour < 15 else d.date()


def build_report(state: dict, now: dt.datetime) -> str:
    bets = state.get("bets", {})
    day = report_day(now)
    day_bets = sorted([b for b in bets.values() if parse_ts(b["start"]).astimezone(ATHENS).date() == day],
                      key=lambda b: b["start"])
    settled_all = [b for b in bets.values() if b["status"] == "settled"]
    since = state.get("stats_since")
    since_txt = f" (από {parse_ts(since).astimezone(ATHENS):%d/%m})" if since else ""
    lines = [f"📊 <b>ΑΠΟΛΟΓΙΣΜΟΣ · {GR_DAYS[day.weekday()]} {day:%d/%m}</b>",
             "<i>Ποσό = όσα έγραψες με απάντηση στο Telegram · χωρίς απάντηση = δεν παίχτηκε (▫️)</i>", ""]
    icons = {"WIN": "✅", "HALFWIN": "✅½", "LOSE": "❌", "HALFLOSS": "❌½", "PUSH": "↩️", "CANCELLED": "↩️"}
    if day_bets:
        for b in day_bets:
            clv = f" · CLV {b['clv']:+.1f}%" if "clv" in b else ""
            kind_icon = "📢 " if b.get("kind") == "steam" else ""
            stake = b.get("stake", C.STAKE)
            st_txt = " · δεν παίχτηκε" if stake == 0 else f" · {stake:g}€"
            head = f"{kind_icon}{html.escape(b['match'])} · {html.escape(b['pick'])} @{b['price']:.2f}{st_txt}"
            if b["status"] == "settled" and stake == 0 and not b.get("suggested"):
                lines.append(f"▫️{icons.get(b['result'], '•')} {head}{clv}")
            elif b["status"] == "settled" and stake == 0:
                lines.append(f"▫️{icons.get(b['result'], '•')} {head} (με το προτεινόμενο "
                             f"{b.get('suggested', 0):g}€ θα ήταν {virtual_pnl(b):+.2f}€){clv}")
            elif b["status"] == "settled":
                lines.append(f"{icons.get(b['result'], '•')} {head} → <b>{bet_pnl(b):+.2f}€</b>{clv}")
            elif b["status"] == "unknown":
                lines.append(f"❔ {head} → δεν βρέθηκε αποτέλεσμα{clv}")
            else:
                lines.append(f"⏳ {head} → εκκρεμεί{clv}")
        done = [b for b in day_bets if b["status"] == "settled"]
        staked = sum(b.get("stake", C.STAKE) for b in done)
        lines += ["", f"📅 Έπαιξες: {_summary(done)} · ποντάρισες {staked:g}€",
                  f"📐 Αν έπαιζες όλες τις ειδοποιήσεις: {_virtual_summary(done)}"]
        pend = sum(1 for b in day_bets if b["status"] == "open")
        if pend:
            lines.append(f"⏳ Εκκρεμούν {pend} — θα μετρηθούν μόλις βγει το αποτέλεσμα")
    else:
        lines.append("Δεν βγήκαν ειδοποιήσεις αυτή τη μέρα.")
    day_t = [t for t in state.get("tickets", {}).values() if t["date"] == day.strftime("%Y-%m-%d")]
    if day_t:
        lines += ["", "🎟️ <b>Δελτία</b>"]
        for t in day_t:
            st = t.get("stake")
            res = {"WIN": "✅", "LOSE": "❌"}.get(t.get("result"), "⏳")
            stake_txt = "δεν παίχτηκε" if not st else f"{st:g}€"
            pnl = f" → <b>{ticket_pnl(t):+.2f}€</b>" if t.get("result") and st else ""
            lines.append(f"{res} {html.escape(t['name'])} @{t['odds']:.2f} · {stake_txt}{pnl}")
    all_t = [t for t in state.get("tickets", {}).values() if t.get("result") and t.get("stake")]
    bank = bankroll(state)
    lines += ["", f"💼 Κάσα: {C.BANKROLL:g}€ → <b>{bank:.2f}€</b> ({bank - C.BANKROLL:+.2f}€)",
              f"📈 <b>Από την αρχή{since_txt} — όσα έπαιξες:</b> {_summary(settled_all)}",
              f"📐 <b>Όλες οι ειδοποιήσεις (προτεινόμενα ποσά):</b> {_virtual_summary(settled_all)}"]
    for kind, lab in (("value", "🔥 Αξία"), ("steam", "📢 Λεφτά")):
        sub = [b for b in settled_all if b.get("kind", "value") == kind]
        if sub:
            lines.append(f"   {lab}: {_virtual_summary(sub)}")
    if all_t:
        w = sum(1 for t in all_t if t["result"] == "WIN")
        tp = sum(ticket_pnl(t) for t in all_t)
        lines.append(f"   🎟️ Δελτία: {len(all_t)} · {w}✅ {len(all_t) - w}❌ · PnL <b>{tp:+.2f}€</b>")
    for st in (2, 3):
        sub = [b for b in settled_all if b.get("stars") == st]
        if sub:
            lines.append(f"   {'⭐' * st}: {_virtual_summary(sub)}")
    dl = diag_line(state, dt.datetime.combine(day, dt.time(12), tzinfo=ATHENS))
    if dl:
        lines += ["", dl.replace("Σήμερα:", "Η μέρα:")]
    clv = _clv_summary(list(bets.values()))
    if clv:
        lines += ["", clv,
                  "<i>CLV = πόσο καλύτερη ήταν η απόδοσή μας από την τελική του Pinnacle πριν τη σέντρα. "
                  "Θετικό σταθερά = το σύστημα κερδίζει μακροπρόθεσμα, ανεξάρτητα από την τύχη.</i>"]
    return "\n".join(lines)


def maybe_report(state: dict, now: dt.datetime, force: bool = False) -> bool:
    d = now.astimezone(ATHENS)
    today = d.strftime("%Y-%m-%d")
    hh, mm = (int(x) for x in C.REPORT_TIME.split(":"))
    if not force and (state.get("last_report") == today or (d.hour, d.minute) < (hh, mm)):
        return False
    # περιμένει (έως 2 ώρες) να κλείσουν όσα στοιχήματα της μέρας δεν έχουν αποτέλεσμα ακόμα
    day = report_day(now)
    pending = [b for b in state.get("bets", {}).values() if b["status"] == "open"
               and parse_ts(b["start"]).astimezone(ATHENS).date() == day]
    if not force and pending and (d.hour, d.minute) < (hh + 2, mm):
        return False
    send_telegram(build_report(state, now))
    for b in state.get("bets", {}).values():
        if b["status"] in ("settled", "unknown"):
            b["reported"] = True
    if not force:
        state["last_report"] = today
    return True


def prune_bets(state: dict, now: dt.datetime) -> None:
    cutoff = iso(now - dt.timedelta(days=C.KEEP_BETS_DAYS))
    state["bets"] = {k: b for k, b in state.get("bets", {}).items() if b["start"] >= cutoff}
    state["tickets"] = {k: t for k, t in state.get("tickets", {}).items() if t["last_start"] >= cutoff}
    state["cands"] = {k: v for k, v in state.get("cands", {}).items()
                      if v and parse_ts(v[0]["start"]) > now - dt.timedelta(hours=3)}


# ---------------------------------------------------------------- Main ---------
def prune(state: dict, now: dt.datetime) -> None:
    cutoff = now - dt.timedelta(days=2)
    state["alerts"] = {k: v for k, v in state.get("alerts", {}).items()
                       if parse_ts(v["start"]) > cutoff}
    alive = {f["fixtureId"] for f in state.get("fixtures", [])}
    state["checked"] = {k: v for k, v in state.get("checked", {}).items() if k in alive}
    state.pop("bf_checked", None)


def run(dry: bool = False) -> None:
    started = time.monotonic()
    if not C.ODDSPAPI_KEY:
        sys.exit("Λείπει το ODDSPAPI_KEY")
    if not dry and not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
        sys.exit("Λείπουν TELEGRAM_TOKEN / TELEGRAM_CHAT_ID")
    state = load_state()
    apply_slug_fixes(state.get("slug_fix", {}))
    now = dt.datetime.now(dt.timezone.utc)
    if state.get("stats_reset") != C.STATS_RESET:
        old = len(state.get("bets", {}))
        state["bets"] = {}
        state["stats_reset"] = C.STATS_RESET
        state["stats_since"] = iso(now)
        log.info("Μηδενισμός στατιστικών (%s): σβήστηκαν %d παλιά στοιχήματα", C.STATS_RESET, old)
        if not dry:
            try:
                send_telegram("🔄 <b>Νέο ξεκίνημα στατιστικών</b>\nΤο PnL μετράει από τώρα και στο εξής.")
            except Exception:
                pass
    try:
        refresh_markets(state, now)
        refresh_fixtures(state, now)
    except QuotaExceeded:
        log.error("Τελείωσαν τα μηνιαία αιτήματα του OddsPapi.")
        save_state(state)
        return
    markets = resolve_markets(state.get("market_catalog", []))
    log.info("Αγορές: %s", ", ".join(f"{v['name']} [{k}]" for k, v in markets.items()))
    if not dry:
        try:
            process_replies(state)
        except Exception as e:
            log.warning("Telegram απαντήσεις: %s", e)
    try:
        compute_clv(state, now)
    except Exception as e:
        log.warning("CLV: %s", e)
    try:
        settle_bets(state, now)
    except Exception as e:
        log.warning("Αποτελέσματα: %s", e)
    fixtures = select_fixtures(state, now)
    sent = skipped = held = confirmed_n = below = 0
    DIAG.clear()
    cat = {str(m.get("marketId")): m for m in state.get("market_catalog", [])}
    quiet = in_quiet_hours(now)
    if quiet:
        log.info("Ήσυχες ώρες: στέλνονται μόνο σοβαρές περιπτώσεις")
    for fx in fixtures:
        if time.monotonic() - started > C.MAX_RUNTIME_SEC:
            log.warning("Όριο χρόνου — συνέχεια στον επόμενο γύρο")
            break
        try:
            hist = fetch_history(fx["fixtureId"], state)
        except QuotaExceeded:
            log.error("Τελείωσαν τα μηνιαία αιτήματα του OddsPapi.")
            break
        except Exception as e:
            log.warning("%s: %s", fx["fixtureId"], e)
            continue
        state.setdefault("checked", {})[fx["fixtureId"]] = iso(now)
        _diag("fixtures", fx["fixtureId"])
        if C.REQUIRE_ALL_BOOKS and not has_all_books(hist, markets):
            skipped += 1
            continue
        t = dt.datetime.now(dt.timezone.utc)
        sigs = analyze(fx, hist, t, markets)
        if C.TICKETS_ENABLED:
            try:
                collect_candidates(state, fx, hist, t, cat, markets)
            except Exception as e:
                log.info("Υποψήφια δελτίων %s: %s", fx["fixtureId"], e)
        if any((sg["values"] or sg.get("steam")) and not sg["live"] for sg in sigs):
            try:
                fetch_confirmations(fx, hist, [sg for sg in sigs if sg["values"] or sg.get("steam")], state)
                confirmed_n += 1
            except QuotaExceeded:
                log.error("Τελείωσαν τα μηνιαία αιτήματα του OddsPapi.")
                break
            sigs = analyze(fx, hist, t, markets)
        for sig in sigs:
            if stars(sig) < C.MIN_STARS:
                below += 1
                continue
            _diag("alert", f"{fx['fixtureId']}|{sig['market']}|{sig['outcome']}")
            if quiet:
                if not is_serious(sig):
                    held += 1  # δεν καταγράφεται → θα σταλεί μετά τις ήσυχες ώρες αν ισχύει ακόμα
                    continue
                sig["quiet"] = True
            if should_alert(state, sig):
                sig["stake"] = suggest_stake(sig, state) if sig["values"] else steam_stake(state)
                sig["bank"] = bankroll(state)
                msg = format_signal(sig)
                if dry:
                    print("\n" + msg + "\n" + "-" * 40)
                else:
                    try:
                        mid = send_telegram(msg)
                    except Exception as e:
                        log.error("Αποστολή απέτυχε: %s", e)
                        continue
                    record_bet(state, sig, mid)
                sent += 1
    save_diag(state, now)
    if not dry:
        try:
            maybe_send_tickets(state, now)
        except Exception as e:
            log.warning("Δελτία: %s", e)
        try:
            maybe_report(state, now)
        except Exception as e:
            log.warning("Απολογισμός: %s", e)
    prune(state, now)
    prune_bets(state, now)
    save_state(state)
    log.info("Τέλος γύρου: %d ειδοποιήσεις, %d σε αναμονή (ήσυχες ώρες), %d με λιγότερα από %d ⭐, "
             "%d αγώνες χωρίς αποδόσεις σε όλα τα site, %d αγώνες με έλεγχο επιπλέον πηγών",
             sent, held, below, C.MIN_STARS, skipped, confirmed_n)


def list_leagues() -> None:
    """Δείχνει όλες τις λίγκες της λίστας αγώνων με τα IDs τους."""
    state = load_state()
    if not state.get("fixtures"):
        if not C.ODDSPAPI_KEY:
            sys.exit("Λείπει το ODDSPAPI_KEY")
        refresh_fixtures(state, dt.datetime.now(dt.timezone.utc))
        save_state(state)
    counts: dict = {}
    slugs = {f.get("tournamentId"): f.get("categorySlug") or "" for f in state["fixtures"]}
    for f in state["fixtures"]:
        k = (f.get("tournamentId"), f.get("categoryName") or "", f.get("tournamentName") or "")
        counts[k] = counts.get(k, 0) + 1

    def ok(tid, cat, tname):
        return league_ok({"tournamentId": tid, "categoryName": cat, "tournamentName": tname,
                          "categorySlug": slugs.get(tid, "")})

    print(f"{'':2} {'ID':>6}  {'Χώρα':<22} {'Λίγκα':<40} Αγώνες")
    for (tid, cat, tname), n in sorted(counts.items(), key=lambda x: (x[0][1], x[0][2])):
        print(f"{'✅' if ok(tid, cat, tname) else '  '} {tid!s:>6}  {cat[:22]:<22} {tname[:40]:<40} {n}")
    watched = sum(n for k, n in counts.items() if ok(*k))
    print(f"\n✅ = παρακολουθείται · {watched} από {sum(counts.values())} αγώνες τις επόμενες 47 ώρες")


def list_markets() -> None:
    """Δείχνει ποιες αγορές βρήκε το bot και όλες τις υποψήφιες του καταλόγου."""
    state = load_state()
    if not C.ODDSPAPI_KEY and not state.get("market_catalog"):
        sys.exit("Λείπει το ODDSPAPI_KEY")
    refresh_markets(state, dt.datetime.now(dt.timezone.utc))
    save_state(state)
    res = resolve_markets(state["market_catalog"])
    print("ΑΓΟΡΕΣ ΠΟΥ ΠΑΡΑΚΟΛΟΥΘΟΥΝΤΑΙ:")
    for k, v in res.items():
        print(f"  ✅ [{k}] {v['name']} → {', '.join(v['outcomes'].values())[:80]}")
    print("\nΥΠΟΨΗΦΙΕΣ ΣΤΟΝ ΚΑΤΑΛΟΓΟ (γκολ, σκορ, αποτέλεσμα):")
    for m in state["market_catalog"]:
        n = norm(m.get("marketName"))
        if any(x in n for x in ("over", "under", "total", "score", "result", "1x2")):
            mark = "✅" if str(m.get("marketId")) in res else "  "
            print(f"  {mark} [{m.get('marketId')}] {m.get('marketName')} · period={m.get('period')}"
                  f" · line={m.get('handicap')} · type={m.get('marketType')}")


def debug() -> None:
    """Δοκιμή exchange (Betfair/Matchbook): τυπώνει τι πληροφορίες δίνει το API (απόδοση, ποσά, ρευστότητα)."""
    if not C.ODDSPAPI_KEY:
        sys.exit("Λείπει το ODDSPAPI_KEY")
    state = load_state()
    now = dt.datetime.now(dt.timezone.utc)
    refresh_fixtures(state, now)
    save_state(state)
    cands = sorted([f for f in state.get("fixtures", [])
                    if league_ok(f) and now - dt.timedelta(minutes=100) < parse_ts(f["startTime"])
                    <= now + dt.timedelta(hours=30)], key=lambda f: f["startTime"])
    if not cands:
        sys.exit("Δεν βρέθηκαν αγώνες")
    labels = {101: "1", 102: "X", 103: "2", 1010: "Over 2.5", 1011: "Under 2.5"}

    def get(fid, book, oid):
        time.sleep(COOLDOWN["historical-odds"])
        prm = {"fixtureId": fid, "bookmakers": book, "apiKey": C.ODDSPAPI_KEY}
        if oid is not None:
            prm["outcomeId"] = oid
        return requests.get(f"{API}/historical-odds", timeout=40, params=prm)

    for fx in cands[:3]:
        fid = fx["fixtureId"]
        start = parse_ts(fx["startTime"]).astimezone(ATHENS)
        print("=" * 90)
        print(f"Αγώνας: {fx.get('participant1Name')} – {fx.get('participant2Name')} "
              f"({fx.get('categoryName')} · {fx.get('tournamentName')}) · {start:%d/%m %H:%M}")
        r = get(fid, ",".join(C.CONFIRM_BOOKS[:3]), None)
        try:
            bms = r.json().get("bookmakers") or {} if r.ok else {}
            print(f"  {','.join(C.CONFIRM_BOOKS)}: {r.status_code} · " + (", ".join(
                f"{b} ({len((v or {}).get('markets') or {})} αγορές)" for b, v in bms.items()) or r.text[:200]))
        except Exception:
            print(f"  {','.join(C.CONFIRM_BOOKS)}: {r.status_code} {r.text[:200]}")
        found = False
        for book in ("betfair-ex",):
            for oid, lab in labels.items():
                if book == "matchbook" and oid not in (101, 1010):
                    continue
                r = get(fid, book, oid)
                if not r.ok:
                    print(f"  {book} {lab}: {r.status_code} {r.text[:200]}")
                    continue
                rows = []
                try:
                    for bm in (r.json().get("bookmakers") or {}).values():
                        for mk in (bm.get("markets") or {}).values():
                            for oc in (mk.get("outcomes") or {}).values():
                                for pl in (oc.get("players") or {}).values():
                                    rows += pl or []
                except Exception as e:
                    print(f"  {book} {lab}: λάθος ανάγνωσης {e}: {r.text[:200]}")
                    continue
                rows.sort(key=lambda x: x.get("createdAt") or "")
                keys = sorted({k for x in rows for k in (x.get("exchangeMeta") or {})})
                print(f"  {book} {lab}: {len(rows)} εγγραφές · πεδία exchangeMeta: {keys or '—'}")
                for x in rows[-2:]:
                    print("     ", json.dumps({k: x.get(k) for k in ("createdAt", "price", "limit", "exchangeMeta")},
                                               ensure_ascii=False)[:500])
                found = found or bool(rows)
        if found:
            break
    print("\nΤΕΛΟΣ ΔΟΚΙΜΗΣ")


def main() -> None:
    args = set(sys.argv[1:])
    if "--test-telegram" in args:
        send_telegram("✅ Το Odds Bot συνδέθηκε σωστά! Θα λαμβάνεις εδώ τις ειδοποιήσεις.")
        print("Στάλθηκε.")
        test_alert()
        st = load_state()
        try:
            maybe_send_tickets(st, dt.datetime.now(dt.timezone.utc), force=True, test=True)
        except Exception as e:
            log.warning("Δοκιμή δελτίων: %s", e)
        send_telegram("🧪 <b>ΔΟΚΙΜΗ απολογισμού</b> (έτσι θα έρχεται κάθε βράδυ)\n\n"
                      + build_report(st, dt.datetime.now(dt.timezone.utc)))
    elif "--leagues" in args:
        list_leagues()
    elif "--markets" in args:
        list_markets()
    elif "--debug" in args:
        debug()
    elif "--quota" in args:
        print(json.dumps(api_get("account"), indent=2, ensure_ascii=False))
    else:
        run(dry="--dry-run" in args)


if __name__ == "__main__":
    main()
