"""Στατιστικά ομάδων από το football-data.co.uk (δωρεάν CSV, χωρίς κλειδί).

- Κατεβάζει τα αποτελέσματα της τρέχουσας και της προηγούμενης σεζόν (γκολ, γκολ ημιχρόνου, κόρνερ).
- Υπολογίζει για κάθε αγώνα πόσα γκολ / κόρνερ περιμένουμε και την πιθανότητα για Over/Under.
- Βρίσκει αποτελέσματα αγώνων (για να μη χρεώνονται αιτήματα του OddsPapi).
"""
from __future__ import annotations

import csv
import datetime as dt
import difflib
import io
import logging
import math
import re
import unicodedata

import requests

import config as C

log = logging.getLogger("odds-bot")

BASE = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"

# (χώρες όπως τις γράφει το OddsPapi, μοτίβο ονόματος λίγκας, κωδικός football-data)
LEAGUES = [
    (("england",), r"^premier league$", "E0"),
    (("england",), r"^championship$", "E1"),
    (("england",), r"^league one$", "E2"),
    (("england",), r"^league two$", "E3"),
    (("england",), r"^national league$", "EC"),
    (("scotland",), r"^premiership$", "SC0"),
    (("scotland",), r"^championship$", "SC1"),
    (("scotland",), r"^league (one|1)$", "SC2"),
    (("scotland",), r"^league (two|2)$", "SC3"),
    (("germany",), r"^bundesliga$", "D1"),
    (("germany",), r"^2\. bundesliga$", "D2"),
    (("italy",), r"^serie a$", "I1"),
    (("italy",), r"^serie b$", "I2"),
    (("spain",), r"^laliga$|^la liga$", "SP1"),
    (("spain",), r"laliga 2|la liga 2|hypermotion|segunda", "SP2"),
    (("france",), r"^ligue 1$", "F1"),
    (("france",), r"^ligue 2$", "F2"),
    (("netherlands",), r"^eredivisie$", "N1"),
    (("belgium",), r"pro league|first division a|jupiler", "B1"),
    (("portugal",), r"^liga portugal$|primeira", "P1"),
    (("turkey", "turkiye"), r"super lig", "T1"),
    (("greece",), r"super league", "G1"),
]

STOP = {"fc", "afc", "cf", "sc", "ac", "as", "ss", "us", "sv", "vfb", "vfl", "fk", "sk", "cd", "ud", "rc",
        "rcd", "real", "club", "de", "la", "the", "1", "calcio", "sporting", "athletic", "ad", "ca", "sd", "if"}
SYN = {"united": "utd", "city": "city", "saint": "st", "wanderers": "wand", "hotspur": "", "albion": "",
       "manchester": "man", "nottingham": "nottm", "sheffield": "sheff", "wednesday": "weds",
       "borussia": "", "monchengladbach": "mgladbach", "internazionale": "inter", "olympique": ""}


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _tokens(name: str) -> list[str]:
    out = []
    for t in _norm(name).split():
        t = SYN.get(t, t)
        if t and t not in STOP:
            out.append(t)
    return out


def season_codes(now: dt.datetime) -> list[str]:
    y = now.year % 100 if now.month >= 7 else (now.year - 1) % 100
    return [f"{y:02d}{(y + 1) % 100:02d}", f"{(y - 1) % 100:02d}{y:02d}"]


def league_code(fx: dict) -> str | None:
    cat = _norm(fx.get("categoryName") or fx.get("categorySlug")).replace(" ", "-")
    name = _norm(fx.get("tournamentName"))
    for countries, pat, code in LEAGUES:
        if any(cat == c.replace(" ", "-") for c in countries) and re.search(pat, name):
            return code
    return None


def _num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _date(v: str) -> str | None:
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(v.strip(), f).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            pass
    return None


def parse_csv(text: str) -> list[list]:
    """→ [ημερομηνία, γηπεδούχος, φιλοξενούμενος, γκολ Γ, γκολ Φ, γκολ ημ. Γ, γκολ ημ. Φ, κόρνερ Γ, κόρνερ Φ]"""
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        d = _date(r.get("Date") or "")
        h, a = (r.get("HomeTeam") or r.get("Home") or "").strip(), (r.get("AwayTeam") or r.get("Away") or "").strip()
        fh, fa = _num(r.get("FTHG") or r.get("HG")), _num(r.get("FTAG") or r.get("AG"))
        if not d or not h or not a or fh is None or fa is None:
            continue
        rows.append([d, h, a, fh, fa, _num(r.get("HTHG")), _num(r.get("HTAG")), _num(r.get("HC")), _num(r.get("AC"))])
    return rows


def fetch(code: str, season: str) -> list[list]:
    r = requests.get(BASE.format(season=season, code=code), timeout=30,
                     headers={"User-Agent": "odds-bot (personal use)"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    raw = r.content
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return parse_csv(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return []


def trim(rows: list[list], keep: int) -> list[list]:
    """Κρατάει μόνο τους τελευταίους `keep` αγώνες κάθε ομάδας (για να μένει μικρό το state)."""
    rows = sorted(rows, key=lambda r: r[0], reverse=True)
    cnt: dict[str, int] = {}
    out = []
    for r in rows:
        if cnt.get(r[1], 0) < keep or cnt.get(r[2], 0) < keep:
            out.append(r)
        cnt[r[1]] = cnt.get(r[1], 0) + 1
        cnt[r[2]] = cnt.get(r[2], 0) + 1
    return sorted(out, key=lambda r: r[0])


def refresh(state: dict, now: dt.datetime, fixtures: list[dict], force: bool = False) -> int:
    """Κατεβάζει (μία φορά ανά STATS_REFRESH_HOURS) τις λίγκες που έχουν αγώνες τις επόμενες μέρες."""
    if not C.STATS_ENABLED:
        return 0
    store = state.setdefault("stats", {})
    need = {league_code(f) for f in fixtures} - {None}
    # και όσες λίγκες έχουν ανοιχτά στοιχήματα (για τα αποτελέσματα)
    need |= {b.get("lg") for b in state.get("bets", {}).values() if b.get("status") == "open"} - {None}
    need |= {league_code(l["fxi"]) for t in state.get("tickets", {}).values() if not t.get("result")
             for l in t.get("leg_data", []) if l.get("fxi")} - {None}
    done = 0
    for code in sorted(need):
        ent = store.get(code) or {}
        if not force and ent.get("at") and \
                now - dt.datetime.fromisoformat(ent["at"].replace("Z", "+00:00")) < dt.timedelta(hours=C.STATS_REFRESH_HOURS):
            continue
        rows = []
        try:
            for s in season_codes(now):
                rows += fetch(code, s)
        except Exception as e:
            log.info("Στατιστικά %s: %s", code, str(e)[:120])
            retry = now - dt.timedelta(hours=max(0, C.STATS_REFRESH_HOURS - 1))   # ξαναδοκιμάζει σε ~1 ώρα
            ent["at"] = retry.strftime("%Y-%m-%dT%H:%M:%SZ")
            store[code] = ent
            continue
        store[code] = {"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": trim(rows, C.STATS_KEEP_MATCHES)}
        done += 1
    return done


# ------------------------------------------------------------------ ομάδες --
BUILTIN_ALIASES = {
    "wolverhampton wanderers": "Wolves", "wolverhampton": "Wolves", "heart of midlothian": "Hearts",
    "sporting cp": "Sp Lisbon", "sporting lisbon": "Sp Lisbon", "sporting braga": "Sp Braga", "sc braga": "Sp Braga",
    "queens park rangers": "QPR", "vitoria guimaraes": "Guimaraes", "vitoria sc": "Guimaraes",
    "paris saint germain": "Paris SG", "west bromwich albion": "West Brom", "brighton and hove albion": "Brighton",
    "atletico madrid": "Ath Madrid", "athletic club": "Ath Bilbao", "athletic bilbao": "Ath Bilbao",
    "rayo vallecano": "Vallecano", "deportivo alaves": "Alaves", "celta vigo": "Celta",
    "bayer leverkusen": "Leverkusen", "rb leipzig": "RB Leipzig", "fc koln": "FC Koln", "1 fc koln": "FC Koln",
    "st pauli": "St Pauli", "fc st pauli": "St Pauli", "inter milan": "Inter", "internazionale": "Inter",
    "az alkmaar": "AZ Alkmaar", "go ahead eagles": "Go Ahead Eagles", "union saint gilloise": "St. Gilloise",
    "royale union saint gilloise": "St. Gilloise", "olympiacos": "Olympiakos", "olympiacos piraeus": "Olympiakos",
    "ofi crete": "OFI Crete", "aris thessaloniki": "Aris", "istanbul basaksehir": "Buyuksehyr",
}


def match_team(names: list[str], teams: set[str]) -> str | None:
    """Ονόματα από το OddsPapi → όνομα ομάδας στο CSV."""
    alias = {**{k: v for k, v in BUILTIN_ALIASES.items()},
             **{_norm(k): v for k, v in getattr(C, "TEAM_ALIASES", {}).items()}}
    for n in names:
        if _norm(n) in alias and alias[_norm(n)] in teams:
            return alias[_norm(n)]
    by_norm = {_norm(t): t for t in teams}
    for n in names:
        if _norm(n) in by_norm:
            return by_norm[_norm(n)]
    best, best_s = None, 0.0
    for n in names:
        tn = _tokens(n)
        if not tn:
            continue
        for t in teams:
            tt = _tokens(t)
            if not tt:
                continue
            common = len(set(tn) & set(tt))
            ratio = difflib.SequenceMatcher(None, " ".join(tn), " ".join(tt)).ratio()
            prefix = any(a.startswith(b) or b.startswith(a) for a in tn for b in tt if min(len(a), len(b)) >= 4)
            subset = set(tt) <= set(tn) or set(tn) <= set(tt)   # π.χ. "Ajax" ⊂ "Ajax Amsterdam"
            s = ratio + 0.25 * common + (0.15 if prefix else 0) + (0.3 if subset and common else 0)
            if s > best_s:
                best, best_s = t, s
    return best if best_s >= 0.85 else None


def _teams(fx: dict) -> tuple[list[str], list[str]]:
    return ([fx.get("participant1Name"), fx.get("participant1ShortName")],
            [fx.get("participant2Name"), fx.get("participant2ShortName")])


def resolve(state: dict, fx: dict) -> tuple[str, str, str, list[list]] | None:
    code = league_code(fx)
    rows = ((state.get("stats") or {}).get(code) or {}).get("rows") if code else None
    if not rows:
        return None
    teams = {r[1] for r in rows} | {r[2] for r in rows}
    hn, an = _teams(fx)
    h, a = match_team([n for n in hn if n], teams), match_team([n for n in an if n], teams)
    if not h or not a or h == a:
        return None
    return code, h, a, rows


# ------------------------------------------------------------------ μοντέλο --
COLS = {"goals": (3, 4), "ht": (5, 6), "corners": (7, 8)}


def _rates(rows: list[list], team: str, home: bool, col: tuple[int, int], last: int) -> tuple[float, float, int]:
    """(μέσος όρος υπέρ, κατά, πλήθος) στους τελευταίους `last` αγώνες της ομάδας εντός ή εκτός."""
    side, other = (col[0], col[1]) if home else (col[1], col[0])
    ms = [r for r in rows if (r[1] if home else r[2]) == team and r[side] is not None and r[other] is not None]
    ms = ms[-last:]
    if not ms:
        return 0.0, 0.0, 0
    return sum(r[side] for r in ms) / len(ms), sum(r[other] for r in ms) / len(ms), len(ms)


def expected(rows: list[list], home: str, away: str, stat: str) -> tuple[float, float, int] | None:
    """Αναμενόμενα γκολ/κόρνερ γηπεδούχου και φιλοξενούμενου (πολλαπλασιαστικό μοντέλο επίθεσης/άμυνας)."""
    col = COLS[stat]
    valid = [r for r in rows if r[col[0]] is not None and r[col[1]] is not None]
    if len(valid) < 30:
        return None
    avg_h = sum(r[col[0]] for r in valid) / len(valid)
    avg_a = sum(r[col[1]] for r in valid) / len(valid)
    if avg_h <= 0 or avg_a <= 0:
        return None
    k0, last = C.STATS_SHRINK, C.STATS_LAST_MATCHES
    hf, ha, nh = _rates(valid, home, True, col, last)
    af, aa, na = _rates(valid, away, False, col, last)
    if nh + na < C.STATS_MIN_MATCHES or nh < 2 or na < 2:
        return None
    shrink = lambda v, n, prior: (v * n + prior * k0) / (n + k0)
    lam_h = avg_h * (shrink(hf, nh, avg_h) / avg_h) * (shrink(aa, na, avg_h) / avg_h)
    lam_a = avg_a * (shrink(af, na, avg_a) / avg_a) * (shrink(ha, nh, avg_a) / avg_a)
    return lam_h, lam_a, min(nh, na)


def _pmf(k: int, mean: float, disp: float) -> float:
    """Poisson (disp=1) ή αρνητική διωνυμική (διασπορά = disp × μέσος όρος)."""
    if disp <= 1.0001:
        return math.exp(-mean + k * math.log(mean) - math.lgamma(k + 1)) if mean > 0 else float(k == 0)
    r = mean / (disp - 1)
    p = r / (r + mean)
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1) + r * math.log(p) + k * math.log(1 - p))


def p_over(mean: float, line: float, disp: float = 1.0) -> float:
    under = sum(_pmf(k, mean, disp) for k in range(0, int(math.floor(line)) + 1))
    return max(0.0, min(1.0, 1 - under))


def predict(state: dict, fx: dict) -> dict | None:
    """Πρόβλεψη για τον αγώνα: αναμενόμενα γκολ, γκολ ημιχρόνου, κόρνερ."""
    res = resolve(state, fx)
    if not res:
        return None
    code, h, a, rows = res
    out = {"code": code, "home": h, "away": a}
    for stat in ("goals", "ht", "corners"):
        e = expected(rows, h, a, stat)
        if e:
            out[stat] = round(e[0] + e[1], 2)
            out[stat + "_n"] = e[2]
    return out if len(out) > 3 else None


def prob(pred: dict | None, stat: str, line: float, side: str) -> float | None:
    """Πιθανότητα για Over/Under `line` σε γκολ (goals), γκολ ημιχρόνου (ht) ή κόρνερ (corners)."""
    if not pred or stat not in pred:
        return None
    disp = C.STATS_CORNER_DISPERSION if stat == "corners" else 1.0
    po = p_over(pred[stat], line, disp)
    return po if side == "over" else 1 - po


# ------------------------------------------------------------ αποτελέσματα --
def find_result(state: dict, fx: dict) -> list | None:
    """Η γραμμή του CSV με το αποτέλεσμα του αγώνα (αν έχει ανέβει)."""
    res = resolve(state, fx)
    if not res:
        return None
    _code, h, a, rows = res
    try:
        day = dt.datetime.fromisoformat(fx["startTime"].replace("Z", "+00:00")).date()
    except (KeyError, ValueError):
        return None
    days = {(day + dt.timedelta(days=d)).isoformat() for d in (-1, 0, 1)}
    for r in rows:
        if r[1] == h and r[2] == a and r[0] in days:
            return r
    return None


def settle(row: list, spec: dict) -> str | None:
    """WIN/LOSE/PUSH για μια επιλογή, από τη γραμμή του CSV. spec: stat, line, side."""
    stat, side = spec.get("stat"), spec.get("side")
    if stat == "1x2":
        res = "1" if row[3] > row[4] else ("2" if row[3] < row[4] else "x")
        return "WIN" if side == res else "LOSE"
    if stat == "btts":
        yes = row[3] > 0 and row[4] > 0
        return "WIN" if (side == "yes") == yes else "LOSE"
    col = COLS.get(stat)
    if not col or row[col[0]] is None or row[col[1]] is None:
        return None
    total = row[col[0]] + row[col[1]]
    line = float(spec["line"])
    if total == line:
        return "PUSH"
    return "WIN" if (total > line) == (side == "over") else "LOSE"
