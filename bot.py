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
COOLDOWN = {"historical-odds": 5.3, "fixtures": 2.3, "markets": 1.2, "account": 1.2}
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
        r.raise_for_status()
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
                ok = ("correct score" in name or "exact score" in name) and "team" not in name
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


def select_fixtures(state: dict, now: dt.datetime) -> list[dict]:
    """Σειρά: live → ξεκινούν σύντομα → υπόλοιποι εκ περιτροπής (όποιος ελέγχθηκε παλιότερα)."""
    horizon = now + dt.timedelta(hours=C.LOOKAHEAD_HOURS)
    soon = now + dt.timedelta(hours=C.PRIORITY_HOURS)
    checked = state.get("checked", {})
    out = []
    for f in state.get("fixtures", []):
        if not f.get("startTime") or not league_ok(f):
            continue
        start = parse_ts(f["startTime"])
        if (C.LIVE_ENABLED and is_live(f, now)) or now < start <= horizon:
            out.append(f)

    def prio(f):
        start = parse_ts(f["startTime"])
        group = 0 if start <= now else (1 if start <= soon else 2)
        return (group, checked.get(f["fixtureId"], "") if group == 2 else "", f["startTime"])

    out.sort(key=prio)
    n_live = sum(1 for f in out if parse_ts(f["startTime"]) <= now)
    log.info("%d αγώνες ταιριάζουν στα φίλτρα (%d live)", len(out), n_live)
    return out[: C.MAX_FIXTURES]


def fetch_history(fixture_id: str) -> dict:
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
                        "active": bool(r.get("active", True)), "meta": r.get("exchangeMeta")})
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
    prices = {}
    for o in outcomes:
        cur = current(series(hist, C.SHARP_BOOK, market, o), now, max_age)
        if not cur:
            prices = None
            break
        prices[o] = cur["price"]
    if prices:
        total = sum(1 / p for p in prices.values())
        if 0.9 < total < 1.25:  # λογικό περιθώριο → πλήρης αγορά
            return round(prices[outcome] * total, 3), "Pinnacle"
    if C.USE_BETFAIR:
        bf = current(series(hist, BETFAIR, market, outcome), now, max_age)
        if bf:
            return bf["price"], "Betfair"
    return None, None


def pct_drop(old: float, new: float) -> float:
    return (old - new) / old * 100 if old else 0.0


def analyze(fx: dict, hist: dict, now: dt.datetime, markets: dict) -> list[dict]:
    live = is_live(fx, now)
    max_age = C.LIVE_MAX_PRICE_AGE_MIN if live else None
    edge_min = C.LIVE_VALUE_EDGE_PCT if live else C.VALUE_EDGE_PCT
    check_drops = (not live) or C.LIVE_DROPS
    minute = int((now - parse_ts(fx["startTime"])).total_seconds() // 60) if live else None
    signals = []
    sharp_books = [C.SHARP_BOOK] + ([BETFAIR] if C.USE_BETFAIR else [])
    for m, mk in markets.items():
        hi = mk.get("max_odds", C.MAX_ODDS)
        for o, label in mk["outcomes"].items():
            drops = []
            if check_drops:
                for b in sharp_books:
                    pts = series(hist, b, m, o)
                    cur = current(pts, now, max_age)
                    if not cur or not (C.MIN_ODDS <= cur["price"] <= hi):
                        continue
                    past = price_at(pts, now - dt.timedelta(minutes=C.DROP_WINDOW_MIN)) or pts[0]
                    opening = pts[0]
                    d_win = pct_drop(past["price"], cur["price"])
                    d_open = pct_drop(opening["price"], cur["price"])
                    if d_win >= C.DROP_PCT or d_open >= C.DROP_FROM_OPEN_PCT:
                        drops.append({"book": b, "now": cur["price"], "past": past["price"],
                                      "open": opening["price"], "d_win": d_win, "d_open": d_open,
                                      "meta": cur["meta"]})
            fair, fair_src = fair_odds(hist, m, o, mk["outcomes"], now, max_age)
            greek = []
            for b in C.GREEK_BOOKS:
                cur = current(series(hist, b, m, o), now, max_age)
                if cur:
                    edge = (cur["price"] / fair - 1) * 100 if fair else None
                    greek.append({"book": b, "price": cur["price"], "edge": edge})
            values = [g for g in greek if g["edge"] is not None and g["edge"] >= edge_min
                      and C.MIN_ODDS <= g["price"] <= hi]
            if drops or values:
                signals.append({"fixture": fx, "market": m, "outcome": o, "label": label,
                                "live": live, "minute": minute, "drops": drops, "values": values, "greek": greek,
                                "fair": fair, "fair_src": fair_src, "mk": mk})
    return signals


def should_alert(state: dict, sig: dict) -> bool:
    phase = "live" if sig["live"] else "pre"
    key = f"{sig['fixture']['fixtureId']}|{sig['market']}|{sig['outcome']}|{phase}"
    drop = max([max(d["d_win"], d["d_open"]) for d in sig["drops"]], default=0.0)
    edge = max([v["edge"] for v in sig["values"]], default=0.0)
    alerts = state.setdefault("alerts", {})
    prev = alerts.get(key)
    fire = (prev is None
            or drop >= prev["drop"] + C.REALERT_DROP_STEP
            or edge >= prev["edge"] + C.REALERT_EDGE_STEP
            or (edge > 0 and prev["edge"] <= 0)
            or (drop > 0 and prev["drop"] <= 0))
    if fire:
        alerts[key] = {
            "drop": round(max(drop, prev["drop"] if prev else 0), 2),
            "edge": round(max(edge, prev["edge"] if prev else 0), 2),
            "start": sig["fixture"]["startTime"],
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
    drop = max([max(d["d_win"], d["d_open"]) for d in sig["drops"]], default=0.0)
    edge = max([v["edge"] for v in sig["values"]], default=0.0)
    return bool(sig["drops"] and sig["values"]) or drop >= C.SERIOUS_DROP_PCT \
        or edge >= C.SERIOUS_EDGE_PCT


# ------------------------------------------------------------ Μηνύματα ---------
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
    start = parse_ts(f["startTime"]).astimezone(ATHENS)
    when = f"{GR_DAYS[start.weekday()]} {start:%d/%m %H:%M}"
    if sig["live"]:
        when = f"🔴 LIVE (~{max(sig.get('minute') or 0, 0)}′ από την έναρξη)"
    else:
        when = f"🕒 {when}"

    fire = sig["drops"] and sig["values"]
    head = "🔥 ΠΤΩΣΗ + ΑΞΙΑ" if fire else ("📉 ΠΤΩΣΗ ΑΠΟΔΟΣΗΣ" if sig["drops"] else "💰 ΕΥΚΑΙΡΙΑ ΑΞΙΑΣ")
    if sig.get("quiet"):
        head = "🚨 ΣΟΒΑΡΟ · " + head
    lines = [f"<b>{head}</b>",
             f"⚽ <b>{html.escape(h)} – {html.escape(a)}</b>",
             f"🏆 {html.escape(f.get('tournamentName') or '')} · {when}",
             f"🎯 {html.escape(sig['mk']['name'])}: <b>{html.escape(pick_text(sig, h, a))}</b>", ""]
    for d in sig["drops"]:
        lines.append(f"📉 {name(d['book'])}: {d['past']:.2f} → <b>{d['now']:.2f}</b> "
                     f"(−{d['d_win']:.1f}% σε {C.DROP_WINDOW_MIN}′, −{d['d_open']:.1f}% από αρχή "
                     f"{d['open']:.2f}){meta_text(d['meta'])}")
    if sig["fair"]:
        src = "Pinnacle χωρίς γκανιότα" if sig["fair_src"] == "Pinnacle" else "Betfair"
        lines.append(f"⚖️ Δίκαιη απόδοση ({src}): {sig['fair']:.2f}")
    for g in sig["greek"]:
        mark = "✅" if g in sig["values"] else "▫️"
        edge = f" ({g['edge']:+.1f}%)" if g["edge"] is not None else ""
        lines.append(f"{mark} {name(g['book'])}: <b>{g['price']:.2f}</b>{edge}")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    r = requests.post(f"https://api.telegram.org/bot{C.TELEGRAM_TOKEN}/sendMessage",
                      json={"chat_id": C.TELEGRAM_CHAT_ID, "text": text,
                            "parse_mode": "HTML", "disable_web_page_preview": True},
                      timeout=20)
    if r.status_code != 200:
        log.error("Telegram σφάλμα %s: %s", r.status_code, r.text)
    r.raise_for_status()


# ---------------------------------------------------------------- Main ---------
def prune(state: dict, now: dt.datetime) -> None:
    cutoff = now - dt.timedelta(days=2)
    state["alerts"] = {k: v for k, v in state.get("alerts", {}).items()
                       if parse_ts(v["start"]) > cutoff}
    alive = {f["fixtureId"] for f in state.get("fixtures", [])}
    state["checked"] = {k: v for k, v in state.get("checked", {}).items() if k in alive}


def run(dry: bool = False) -> None:
    started = time.monotonic()
    if not C.ODDSPAPI_KEY:
        sys.exit("Λείπει το ODDSPAPI_KEY")
    if not dry and not (C.TELEGRAM_TOKEN and C.TELEGRAM_CHAT_ID):
        sys.exit("Λείπουν TELEGRAM_TOKEN / TELEGRAM_CHAT_ID")
    state = load_state()
    now = dt.datetime.now(dt.timezone.utc)
    try:
        refresh_markets(state, now)
        refresh_fixtures(state, now)
    except QuotaExceeded:
        log.error("Τελείωσαν τα μηνιαία αιτήματα του OddsPapi.")
        save_state(state)
        return
    markets = resolve_markets(state.get("market_catalog", []))
    log.info("Αγορές: %s", ", ".join(f"{v['name']} [{k}]" for k, v in markets.items()))
    fixtures = select_fixtures(state, now)
    sent = skipped = held = 0
    quiet = in_quiet_hours(now)
    if quiet:
        log.info("Ήσυχες ώρες: στέλνονται μόνο σοβαρές περιπτώσεις")
    for fx in fixtures:
        if time.monotonic() - started > C.MAX_RUNTIME_SEC:
            log.warning("Όριο χρόνου — συνέχεια στον επόμενο γύρο")
            break
        try:
            hist = fetch_history(fx["fixtureId"])
        except QuotaExceeded:
            log.error("Τελείωσαν τα μηνιαία αιτήματα του OddsPapi.")
            break
        except Exception as e:
            log.warning("%s: %s", fx["fixtureId"], e)
            continue
        state.setdefault("checked", {})[fx["fixtureId"]] = iso(now)
        if C.REQUIRE_ALL_BOOKS and not has_all_books(hist, markets):
            skipped += 1
            continue
        for sig in analyze(fx, hist, dt.datetime.now(dt.timezone.utc), markets):
            if quiet:
                if not is_serious(sig):
                    held += 1  # δεν καταγράφεται → θα σταλεί μετά τις ήσυχες ώρες αν ισχύει ακόμα
                    continue
                sig["quiet"] = True
            if should_alert(state, sig):
                msg = format_signal(sig)
                if dry:
                    print("\n" + msg + "\n" + "-" * 40)
                else:
                    try:
                        send_telegram(msg)
                    except Exception as e:
                        log.error("Αποστολή απέτυχε: %s", e)
                        continue
                sent += 1
    prune(state, now)
    save_state(state)
    log.info("Τέλος γύρου: %d ειδοποιήσεις, %d σε αναμονή (ήσυχες ώρες), "
             "%d αγώνες χωρίς αποδόσεις σε όλα τα site", sent, held, skipped)


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


def main() -> None:
    args = set(sys.argv[1:])
    if "--test-telegram" in args:
        send_telegram("✅ Το Odds Bot συνδέθηκε σωστά! Θα λαμβάνεις εδώ τις ειδοποιήσεις.")
        print("Στάλθηκε.")
    elif "--leagues" in args:
        list_leagues()
    elif "--markets" in args:
        list_markets()
    elif "--quota" in args:
        print(json.dumps(api_get("account"), indent=2, ensure_ascii=False))
    else:
        run(dry="--dry-run" in args)


if __name__ == "__main__":
    main()
