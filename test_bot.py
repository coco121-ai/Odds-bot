"""Τεστ λογικής με ψεύτικα δεδομένα (δεν χρειάζεται internet). Τρέξε: python test_bot.py"""
import sys
import datetime as dt

import bot
import config as C

C.MAX_ODDS = 8.0  # τα τεστ χρησιμοποιούν και μεγαλύτερες αποδόσεις
C.BANKROLL = 100  # τα τεστ υπολογίζουν ποντάρισμα με κάσα 100€

C.USE_BETFAIR = True  # τα τεστ ελέγχουν και τη λογική του Betfair
C.GREEK_BOOKS[:] = ["stoiximan", "pamestoixima-gr"]

NOW = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)

# Ψεύτικος κατάλογος αγορών, στη μορφή του /v4/markets
CATALOG = [
    {"marketId": 101, "marketName": "Full Time Result", "handicap": 0, "period": "fulltime",
     "marketType": "1x2", "outcomes": [{"outcomeId": 101, "outcomeName": "1"},
                                       {"outcomeId": 102, "outcomeName": "X"},
                                       {"outcomeId": 103, "outcomeName": "2"}]},
    {"marketId": 104, "marketName": "Both Teams To Score", "handicap": 0, "period": "fulltime",
     "marketType": "totals", "outcomes": [{"outcomeId": 104, "outcomeName": "Yes"},
                                          {"outcomeId": 105, "outcomeName": "No"}]},
    {"marketId": 1010, "marketName": "Over Under Full Time", "handicap": 2.5, "period": "fulltime",
     "marketType": "totals", "outcomes": [{"outcomeId": 1010, "outcomeName": "Over"},
                                          {"outcomeId": 1011, "outcomeName": "Under"}]},
    {"marketId": 1012, "marketName": "Over Under Full Time", "handicap": 3.5, "period": "fulltime",
     "marketType": "totals", "outcomes": [{"outcomeId": 1012, "outcomeName": "Over"},
                                          {"outcomeId": 1013, "outcomeName": "Under"}]},
    {"marketId": 1020, "marketName": "Over Under 1st Half", "handicap": 0.5, "period": "1sthalf",
     "marketType": "totals", "outcomes": [{"outcomeId": 1020, "outcomeName": "Over"},
                                          {"outcomeId": 1021, "outcomeName": "Under"}]},
    {"marketId": 1022, "marketName": "Over Under 1st Half", "handicap": 1.5, "period": "1sthalf",
     "marketType": "totals", "outcomes": [{"outcomeId": 1022, "outcomeName": "Over"},
                                          {"outcomeId": 1023, "outcomeName": "Under"}]},
    {"marketId": 1030, "marketName": "Corners Over Under", "handicap": 2.5, "period": "fulltime",
     "marketType": "totals", "outcomes": [{"outcomeId": 1030, "outcomeName": "Over"},
                                          {"outcomeId": 1031, "outcomeName": "Under"}]},
    {"marketId": 1100, "marketName": "Correct Score", "handicap": 0, "period": "fulltime",
     "marketType": "correctscore", "outcomes": [{"outcomeId": 1100 + i, "outcomeName": s}
                                                for i, s in enumerate(["1:0", "0:0", "1:1", "0:1"])]},
]
CATALOG.append({"marketId": 102053, "marketName": "Correct Score", "handicap": 0,
                "period": "fulltime", "marketType": "correctscore",
                "outcomes": [{"outcomeId": 102053 + i, "outcomeName": n}
                             for i, n in enumerate(["3+", "8+", "10+", "5+", "9"])]})
C.MARKETS.append({"name": "Ακριβές σκορ", "kind": "correct_score", "period": "full", "max_odds": 15.0})
MARKETS = bot.resolve_markets(CATALOG)
C.MARKETS.pop()


def rows(*pairs, now=NOW):
    """pairs: (λεπτά πριν, απόδοση) -> μορφή API (φθίνουσα σειρά όπως στο API)."""
    out = [{"createdAt": (now - dt.timedelta(minutes=m)).isoformat(), "price": p,
            "active": True, "exchangeMeta": None} for m, p in pairs]
    return list(reversed(out))


def book(markets: dict, now=NOW):
    """markets: {marketId: {outcomeId: [(λεπτά πριν, απόδοση), ...]}}"""
    return {"markets": {m: {"outcomes": {o: {"players": {"0": rows(*p, now=now)}}
                                         for o, p in outs.items()}} for m, outs in markets.items()}}


def x12(h, d, a):
    return {"101": {"101": h, "102": d, "103": a}}


FX = {"fixtureId": "idX", "tournamentId": 185, "startTime": "2026-10-10T18:00:00Z",
      "participant1ShortName": "ΠΑΟΚ", "participant2ShortName": "Ολυμπιακός",
      "tournamentName": "Super League", "categorySlug": "greece", "tournamentSlug": "super-league"}

HIST = {
    # Pinnacle: το 2 (φιλοξενούμενος) πέφτει 3.40 -> 2.90 την τελευταία ώρα
    "pinnacle": book(x12([(300, 2.30), (5, 2.55)], [(300, 3.30), (5, 3.35)],
                         [(300, 3.40), (90, 3.40), (5, 2.90)])),
    "betfair-ex": book(x12([(300, 2.32)], [(300, 3.40)], [(300, 3.45), (70, 3.45), (3, 2.96)])),
    # Stoiximan δεν έχει προλάβει: δίνει ακόμα 3.25 στο 2
    "stoiximan": book(x12([(300, 2.25)], [(300, 3.20)], [(300, 3.25)])),
    "pamestoixima-gr": book(x12([(300, 2.20)], [(300, 3.15)], [(300, 2.80)])),
}


def test_resolve_markets():
    names = {k: v["name"] for k, v in MARKETS.items()}
    names.pop("1100", None)
    assert names == {"101": "Τελικό αποτέλεσμα 1Χ2", "1010": "Over/Under 2.5",
                     "1020": "Over/Under Ημιχρόνου (0.5)", "1022": "Over/Under Ημιχρόνου (1.5)"}, names  # όχι BTTS, όχι 3.5, όχι κόρνερ


def test_detects_drop_and_value():
    sigs = bot.analyze(FX, HIST, NOW, MARKETS)
    away = [s for s in sigs if s["outcome"] == "103"]
    assert away, "έπρεπε να βρει σήμα στο 2"
    s = away[0]
    assert {d["book"] for d in s["drops"]} == {"pinnacle", "betfair-ex"}
    assert [v["book"] for v in s["values"]] == ["stoiximan"]
    assert 2.9 < s["fair"] < 3.1 and s["fair_src"] == "Pinnacle"
    print(bot.format_signal(s), "\n")


def test_over25():
    hist = {
        "pinnacle": book({"1010": {"1010": [(200, 2.10), (90, 2.10), (10, 1.80)],
                                   "1011": [(200, 1.80), (10, 2.02)]}}),
        "stoiximan": book({"1010": {"1010": [(200, 2.00)], "1011": [(200, 1.75)]}}),
        "pamestoixima-gr": book({"1010": {"1010": [(200, 1.95)], "1011": [(200, 1.80)]}}),
    }
    sigs = bot.analyze(FX, hist, NOW, MARKETS)
    over = [s for s in sigs if s["outcome"] == "1010"][0]
    assert over["drops"] and over["values"]
    assert bot.pick_text(over, "ΠΑΟΚ", "Ολυμπιακός") == "Over 2.5"
    print(bot.format_signal(over), "\n")


def test_correct_score_uses_betfair_when_no_pinnacle():
    hist = {
        "betfair-ex": book({"1100": {"1100": [(100, 7.0)], "1101": [(100, 9.0)],
                                     "1102": [(100, 6.5)], "1103": [(100, 11.0)]}}),
        "stoiximan": book({"1100": {"1100": [(100, 7.5)]}}),
        "pamestoixima-gr": book({"1100": {"1100": [(100, 6.0)]}}),
    }
    sigs = bot.analyze(FX, hist, NOW, MARKETS)
    s = [x for x in sigs if x["outcome"] == "1100"][0]
    assert s["fair_src"] == "Betfair" and s["values"][0]["book"] == "stoiximan"
    assert bot.pick_text(s, "ΠΑΟΚ", "Ολυμπιακός") == "1:0"


def test_live_only_value_and_fresh_prices():
    live_fx = {**FX, "startTime": (NOW - dt.timedelta(minutes=30)).isoformat()}
    # Live: το 2 πέφτει πολύ (φυσιολογικό), Stoiximan δίνει πολύ πάνω από τη δίκαιη
    hist = {
        "pinnacle": book(x12([(60, 2.3), (2, 1.6)], [(60, 3.3), (2, 3.9)], [(60, 3.4), (2, 6.5)])),
        "stoiximan": book(x12([(60, 2.2), (1, 1.80)], [(60, 3.2), (1, 3.7)], [(60, 3.2), (1, 6.0)])),
        "pamestoixima-gr": book(x12([(60, 2.2), (20, 1.9)], [(60, 3.2)], [(60, 3.2)])),  # παλιές τιμές
    }
    sigs = bot.analyze(live_fx, hist, NOW, MARKETS)
    assert all(not s["drops"] for s in sigs), "στα live δεν στέλνουμε πτώσεις"
    home = [s for s in sigs if s["outcome"] == "101"][0]
    assert home["live"] and [v["book"] for v in home["values"]] == ["stoiximan"]
    assert all(g["book"] != "pamestoixima-gr" for g in home["greek"]), "παλιές τιμές αγνοούνται"
    msg = bot.format_signal(home)
    assert "LIVE" in msg
    print(msg, "\n")


def test_quiet_hours():
    athens = bot.ATHENS
    def at(h):
        return dt.datetime(2026, 10, 10, h, 30, tzinfo=athens)
    assert bot.in_quiet_hours(at(2)) and bot.in_quiet_hours(at(10))
    assert not bot.in_quiet_hours(at(11)) and not bot.in_quiet_hours(at(1))
    fire = [x for x in bot.analyze(FX, HIST, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.is_serious(fire)  # πτώση + αξία μαζί
    small = {**fire, "drops": [], "values": [{"book": "stoiximan", "price": 2.0, "edge": 6.0}]}
    assert not bot.is_serious(small)
    big = {**small, "values": [{"book": "stoiximan", "price": 2.0, "edge": 11.0}]}
    assert not bot.is_serious(big)  # χωρίς πτώση = 1 αστέρι, όχι σοβαρό
    big = dict(fire)
    big["quiet"] = True
    assert bot.format_signal(big).startswith("<b>🚨 ")


def test_fix_slugs():
    err = ('{"error":{"message":"Invalid bookmaker(s) provided.","code":"INVALID_PARAMETER","details":'
           '"Invalid bookmakers: pamestoixima-gr. Valid bookmakers are: 188bet, 1xbet, '
           'pamestoixima.gr, pinnacle, stoiximan, stoiximan.cy"}}')
    assert bot.fix_slugs(["pinnacle", "stoiximan", "pamestoixima-gr"], err) == {"pamestoixima-gr": "pamestoixima.gr"}
    assert bot.fix_slugs(["pinnacle"], "άσχετο λάθος") == {}


def test_correct_score_from_pinnacle_partial():
    scores = {str(1100 + i): [(60, p)] for i, p in enumerate([5, 6, 4.5, 7, 5.5, 6.5, 9, 10])}
    outs = {k: f"{i}:0" for i, k in enumerate(scores)}
    mk = {"9999": {"name": "Ακριβές σκορ", "kind": "correct_score", "line": 0,
                   "outcomes": {**outs, "1200": "4:4"}, "max_odds": 15.0}}
    hist = {"pinnacle": book({"9999": scores}),
            "stoiximan": book({"9999": {"1100": [(60, 9.0)]}})}
    fair, src = bot.fair_odds(hist, "9999", "1100", mk["9999"]["outcomes"])
    assert src == "Pinnacle" and 5 < fair < 8, (fair, src)


def test_no_alert_without_value():
    # Pinnacle πέφτει πολύ αλλά η Stoiximan έχει ήδη χαμηλή απόδοση → καμία ειδοποίηση
    hist = {
        "pinnacle": book(x12([(300, 2.30)], [(300, 3.30)], [(300, 3.40), (90, 3.40), (5, 2.80)])),
        "stoiximan": book(x12([(300, 2.25)], [(300, 3.20)], [(300, 2.40)])),
    }
    assert bot.analyze(FX, hist, NOW, MARKETS) == []  # Stoiximan πολύ κάτω από τη δίκαιη


def test_stars():
    no_bf = {k: v for k, v in HIST.items() if k != "betfair-ex"}
    fire = [x for x in bot.analyze(FX, no_bf, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.stars(fire) == 2  # αξία + πτώση μόνο στο Pinnacle
    only_value = {**fire, "drops": [], "values": [{"book": "stoiximan", "price": 2.0, "edge": 6.0}]}
    assert bot.stars(only_value) == 1
    with_bf = [x for x in bot.analyze(FX, HIST, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.stars(with_bf) == 3  # Pinnacle + Betfair
    msg = bot.format_signal(fire)
    assert "ΜΠΑΙΝΟΥΝ ΛΕΦΤΑ" in msg and "−" not in msg.split("✅")[1].split("\n")[0]


def test_betfair_merge_and_confirm():
    raw = {"bookmakers": {"betfair-ex": {"markets": {"101": {"outcomes": {"103": {"players": {"0": [
        {"createdAt": (NOW - dt.timedelta(minutes=300)).isoformat(), "price": 3.45, "limit": 900},
        {"createdAt": (NOW - dt.timedelta(minutes=70)).isoformat(), "price": 3.45, "limit": 800},
        {"createdAt": (NOW - dt.timedelta(minutes=20)).isoformat(), "price": 2.20, "limit": 4},  # θόρυβος
        {"createdAt": (NOW - dt.timedelta(minutes=3)).isoformat(), "price": 2.96, "limit": 650},
    ]}}}}}}}}
    hist = {k: v for k, v in HIST.items() if k != "betfair-ex"}
    assert bot.merge_betfair(hist, raw) == 3  # η εγγραφή με €4 αγνοείται
    sig = [x for x in bot.analyze(FX, hist, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.confirmed(sig) and bot.stars(sig) == 3
    assert "2 πηγές" in bot.format_signal(sig)


def test_asian_sharp_confirms_with_smaller_drop():
    no_bf = {k: v for k, v in HIST.items() if k != "betfair-ex"}
    # SBOBet πέφτει μόνο 7% (κάτω από το 12% αλλά πάνω από το όριο επιβεβαίωσης 6%)
    no_bf["sbobet"] = book(x12([(300, 2.3)], [(300, 3.3)], [(300, 3.30), (90, 3.30), (4, 3.07)]))
    sig = [x for x in bot.analyze(FX, no_bf, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.stars(sig) == 3, [(d["book"], round(d["d_win"], 1)) for d in sig["drops"]]
    msg = bot.format_signal(sig)
    assert "2 πηγές" in msg and "SBOBet ✅" in msg and "🇬🇷" in msg and "Ελλάδα" in msg, msg
    print(msg, "\n")
    # μόνο μικρή πτώση παντού → καμία "μεγάλη" πηγή → 1 αστέρι
    weak = {"pinnacle": book(x12([(300, 2.3)], [(300, 3.3)], [(300, 3.40), (90, 3.40), (4, 3.15)])),
            "sbobet": no_bf["sbobet"], "stoiximan": book(x12([(300, 2.2)], [(300, 3.1)], [(300, 3.6)]))}
    sig = [x for x in bot.analyze(FX, weak, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.stars(sig) == 1


def test_fetch_confirmations_handles_bad_slug():
    calls = []
    def fake(endpoint, **p):
        calls.append(p)
        if p["bookmakers"].startswith("sbobet"):
            r = type("R", (), {"text": '{"details":"Invalid bookmakers: singbet. Valid bookmakers are: a, b"}'})()
            raise bot.requests.HTTPError("400", response=r)
        return {"bookmakers": {}}
    orig = bot.api_get
    bot.api_get = fake
    try:
        state = {}
        hist = {k: v for k, v in HIST.items() if k != "betfair-ex"}
        sigs = [x for x in bot.analyze(FX, hist, NOW, MARKETS) if x["values"]]
        bot.fetch_confirmations(FX, hist, sigs, state)
        assert state["bad_books"] == ["singbet"]
        assert any(c["bookmakers"] == "betfair-ex" and "outcomeId" in c for c in calls)
        calls.clear()
        bot.fetch_confirmations(FX, hist, sigs, state)
        assert calls[0]["bookmakers"] == "sbobet"  # το λάθος όνομα δεν ξαναζητείται
    finally:
        bot.api_get = orig


def test_flags():
    assert bot.country_flag({"categoryName": "Denmark"})[0] == "🇩🇰"
    assert bot.country_flag({"categoryName": "Turkiye"})[1] == "Τουρκία"
    assert bot.country_flag({"categoryName": "International Clubs",
                             "tournamentName": "UEFA Europa League"})[0] == "🇪🇺"
    assert bot.country_flag({"categoryName": "Kenya", "tournamentName": "Premier League"})[0] == "🌍"


def test_pnl_tracking_and_report():
    state = {}
    no_bf = {k: v for k, v in HIST.items() if k != "betfair-ex"}
    no_bf["sbobet"] = book(x12([(300, 2.3)], [(300, 3.3)], [(300, 3.30), (90, 3.30), (4, 3.07)]))
    sig = [x for x in bot.analyze(FX, no_bf, NOW, MARKETS) if x["outcome"] == "103"][0]
    bot.record_bet(state, sig)
    bot.record_bet(state, sig)  # δεύτερη φορά δεν διπλασιάζεται
    over = {**sig, "market": "1010", "outcome": "1010", "mk": MARKETS["1010"], "label": "Over",
            "values": [{"book": "stoiximan", "price": 2.0, "edge": 6.0}]}
    bot.record_bet(state, over)
    assert len(state["bets"]) == 2
    settle = {"fixtureId": "idX", "markets": {
        "101": {"outcomes": {"103": {"players": {"0": {"result": "WIN"}}}}},
        "1010": {"outcomes": {"1010": {"players": {"0": {"result": "LOSE"}}}}}}}
    calls = []
    orig = bot.api_get
    def fake(endpoint, **p):
        calls.append(endpoint)
        if endpoint == "account":
            return {"subscription": {"request_limit": 250, "request_count": 100}}
        return settle
    bot.api_get = fake
    try:
        later = NOW + dt.timedelta(hours=10)  # ο αγώνας ξεκίνησε 18:00, τώρα 22:00 UTC
        assert bot.settle_bets(state, later) == 1  # 1 αίτημα για τον αγώνα, όχι 2
        assert calls.count("settlements") == 1
    finally:
        bot.api_get = orig
    b = state["bets"]
    win = b["idX|101|103"]; lose = b["idX|1010|1010"]
    assert win["result"] == "WIN" and abs(win["pnl"] - win["stake"] * (3.25 - 1)) < 1e-6
    assert lose["pnl"] == -lose["stake"]
    rep = bot.build_report(state, later)
    assert "ROI" in rep and "⭐⭐⭐" in rep and "Κάσα" in rep, rep
    print(rep, "\n")
    sent = []
    orig_send = bot.send_telegram
    bot.send_telegram = lambda m: sent.append(m)
    try:
        early = dt.datetime(2026, 10, 11, 7, 0, tzinfo=dt.timezone.utc)    # 10:00 Ελλάδας την επόμενη μέρα
        assert not bot.maybe_report(state, early)
        late = dt.datetime(2026, 10, 11, 7, 35, tzinfo=dt.timezone.utc)    # 10:35 Ελλάδας
        assert bot.maybe_report(state, late) and len(sent) == 1
        assert not bot.maybe_report(state, late + dt.timedelta(minutes=10))  # μία φορά τη μέρα
        assert "ΑΠΟΛΟΓΙΣΜΟΣ · Σάβ 10/10" in sent[0], sent[0]  # αφορά την προηγούμενη μέρα
    finally:
        bot.send_telegram = orig_send


def test_settle_respects_daily_cap_and_quota():
    state = {"bets": {f"f{i}|101|101": {"fixtureId": f"f{i}", "market": "101", "outcome": "101",
                                          "match": "m", "pick": "p", "price": 2.0, "stars": 2,
                                          "start": "2026-10-10T10:00:00Z", "status": "open"}
                      for i in range(8)}}
    orig = bot.api_get
    n = {"s": 0}
    def fake(endpoint, **p):
        if endpoint == "account":
            return {"request_limit": 250, "request_count": 222}  # μένουν 28, κρατάμε 25 → 3
        n["s"] += 1
        return {"markets": {}}
    bot.api_get = fake
    try:
        bot.settle_bets(state, NOW + dt.timedelta(hours=5))
    finally:
        bot.api_get = orig
    assert n["s"] == 3, n


def test_pinnacle_limit_filter():
    def rows_lim(lim, *pairs):
        return [{**r, "limit": lim} for r in rows(*pairs)]
    no_bf = {k: v for k, v in HIST.items() if k != "betfair-ex"}
    small = {**no_bf, "pinnacle": {"markets": {"101": {"outcomes": {
        "101": {"players": {"0": rows_lim(300, (300, 2.30), (5, 2.55))}},
        "102": {"players": {"0": rows_lim(300, (300, 3.30), (5, 3.35))}},
        "103": {"players": {"0": rows_lim(300, (300, 3.40), (90, 3.40), (5, 2.90))}}}}}}}
    sig = [x for x in bot.analyze(FX, small, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.stars(sig) == 1  # μικρή αγορά (€300): η πτώση δεν μετράει ως "μεγάλα λεφτά"
    big = {**no_bf, "pinnacle": {"markets": {"101": {"outcomes": {
        o: {"players": {"0": [{**r, "limit": 5000} for r in v["players"]["0"]]}}
        for o, v in small["pinnacle"]["markets"]["101"]["outcomes"].items()}}}}}
    sig = [x for x in bot.analyze(FX, big, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.stars(sig) == 2 and "€5.000" in bot.format_signal(sig) and "μεγάλη αγορά" in bot.format_signal(sig)


def test_clv():
    start = bot.parse_ts(FX["startTime"])  # 18:00 UTC
    def at(h):  # ώρες πριν τη σέντρα
        return (start - dt.timedelta(hours=h)).isoformat()
    hist = {"pinnacle": {"markets": {"101": {"outcomes": {
        "101": {"players": {"0": [{"createdAt": at(5), "price": 2.3, "active": True}]}},
        "102": {"players": {"0": [{"createdAt": at(5), "price": 3.3, "active": True}]}},
        "103": {"players": {"0": [{"createdAt": at(5), "price": 3.4, "active": True},
                                  {"createdAt": at(0.2), "price": 2.8, "active": True},
                                  {"createdAt": (start + dt.timedelta(minutes=5)).isoformat(),
                                   "price": 2.2, "active": True}]}}}}}}}  # live τιμή: αγνοείται
    cf = bot.closing_fair(hist, "101", "103", start)
    assert 2.9 < cf < 3.1, cf
    state = {"bets": {"k": {"fixtureId": "idX", "market": "101", "outcome": "103", "price": 3.25,
                            "start": FX["startTime"], "status": "open", "stars": 3, "match": "m", "pick": "p"}}}
    orig = bot.api_get
    bot.api_get = lambda e, **p: {"bookmakers": hist}
    try:
        bot.compute_clv(state, start + dt.timedelta(minutes=30))
    finally:
        bot.api_get = orig
    b = state["bets"]["k"]
    assert b["clv"] > 0 and b["close"] == cf
    assert "CLV" in bot.build_report(state, start + dt.timedelta(hours=1))


def test_telegram_stake_replies():
    state = {"bets": {"k": {"fixtureId": "f", "market": "101", "outcome": "101", "price": 2.0, "stars": 2,
                            "start": "2026-10-10T10:00:00Z", "status": "settled", "result": "WIN",
                            "match": "m", "pick": "p", "stake": 10, "msg_ids": [555]}}}
    upd = {"ok": True, "result": [
        {"update_id": 7, "message": {"message_id": 900, "chat": {"id": C.TELEGRAM_CHAT_ID or "123"},
                                     "text": "25€", "reply_to_message": {"message_id": 555}}},
        {"update_id": 8, "message": {"message_id": 901, "chat": {"id": "999"},  # άλλο chat → αγνοείται
                                     "text": "0", "reply_to_message": {"message_id": 555}}}]}
    C.TELEGRAM_CHAT_ID = C.TELEGRAM_CHAT_ID or "123"
    sent = []
    orig_get, orig_send = bot.requests.get, bot.send_telegram
    bot.requests.get = lambda *a, **k: type("R", (), {"ok": True, "json": lambda self: upd})()
    bot.send_telegram = lambda m, reply_to=None: sent.append((m, reply_to))
    try:
        assert bot.process_replies(state) == 1
    finally:
        bot.requests.get, bot.send_telegram = orig_get, orig_send
    b = state["bets"]["k"]
    assert b["stake"] == 25 and state["tg_offset"] == 9 and sent[0][1] == 900
    assert bot.bet_pnl(b) == 25.0
    b["stake"] = 0
    assert bot._summary([b]) == "—"  # 0 = δεν παίχτηκε → δεν μετράει


def test_kelly_stake():
    sig = {"values": [{"book": "stoiximan", "price": 2.02, "edge": 7.4}], "fair": 1.88}
    st = bot.suggest_stake(sig, {})          # κάσα 100€
    assert 1 <= st <= 5 and st * 2 == int(st * 2), st
    strong = {"values": [{"book": "stoiximan", "price": 2.40, "edge": 50}], "fair": 1.60}
    assert bot.suggest_stake(strong, {}) == 5.0   # όριο 5% της κάσας
    weak = {"values": [{"book": "stoiximan", "price": 2.00, "edge": 0.5}], "fair": 1.99}
    assert bot.suggest_stake(weak, {}) == C.MIN_STAKE
    state = {"bets": {"a": {"status": "settled", "result": "WIN", "price": 3.0, "stake": 10}}}
    assert bot.bankroll(state) == C.BANKROLL + 20


def test_no_duplicate_functions_and_message_id():
    import re
    src = open(bot.__file__, encoding="utf-8").read()
    names = re.findall(r"^def (\w+)", src, re.M)
    assert len(names) == len(set(names)), [n for n in names if names.count(n) > 1]
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"ok": True, "result": {"message_id": 4242}}
    orig = bot.requests.post
    bot.requests.post = lambda *a, **k: R()
    try:
        assert bot.send_telegram("x") == 4242
    finally:
        bot.requests.post = orig


def test_bankroll_moves_with_stakes():
    b = {"status": "open", "price": 2.0, "stake": 0.0, "start": "2099-01-01T00:00:00Z"}
    state = {"bets": {"a": b}, "tickets": {}}
    assert bot.bankroll(state) == C.BANKROLL
    b["stake"] = 20                                   # το έπαιξα → φεύγει από την κάσα
    assert bot.bankroll(state) == C.BANKROLL - 20
    state["tickets"]["t"] = {"stake": 5, "result": None, "odds": 10, "last_start": "2099-01-01T00:00:00Z"}
    assert bot.bankroll(state) == C.BANKROLL - 25
    b.update(status="settled", result="WIN")          # κέρδισε → γυρνάει 40
    assert bot.bankroll(state) == C.BANKROLL + 20 - 5
    state["tickets"]["t"]["result"] = "LOSE"
    assert bot.bankroll(state) == C.BANKROLL + 20 - 5
    assert "σε εξέλιξη" not in bot.bank_line(state)
    # το κλάδεμα παλιών στοιχημάτων δεν αλλάζει την κάσα
    before = bot.bankroll(state)
    b["start"] = "2000-01-01T00:00:00Z"
    bot.prune_bets(state, NOW)
    assert "a" not in state["bets"] and bot.bankroll(state) == before


def test_test_telegram_mode_runs():
    sent = []
    orig_send, orig_load, orig_argv = bot.send_telegram, bot.load_state, sys.argv
    bot.send_telegram = lambda t, reply_to=None: (sent.append(t), 1)[1]
    bot.load_state = lambda: {"cands": {}, "bets": {}, "tickets": {}}
    sys.argv = ["bot.py", "--test-telegram"]
    try:
        bot.main()
    finally:
        bot.send_telegram, bot.load_state, sys.argv = orig_send, orig_load, orig_argv
    assert any("ΔΟΚΙΜΗ</b> (ψεύτικος" in t for t in sent)
    assert any("ΑΠΟΛΟΓΙΣΜΟΥ" in t.upper() or "απολογισμού" in t for t in sent)


def test_totals_looser_thresholds_and_diag():
    bot.DIAG.clear()
    # Over 2.5: Pinnacle 1.95 → 1.78 (−8.7%) = "μεγάλη" για γκολ, όχι για 1Χ2
    hist = {"pinnacle": book({"1010": {"1010": [(200, 1.95), (90, 1.95), (10, 1.78)],
                                       "1011": [(200, 1.90), (10, 2.08)]}}),
            "stoiximan": book({"1010": {"1010": [(200, 1.98)], "1011": [(200, 1.80)]}})}
    sig = [x for x in bot.analyze(FX, hist, NOW, MARKETS) if x["outcome"] == "1010"][0]
    assert bot.stars(sig) == 2, [(d["book"], d["d_win"], d["strong"]) for d in sig["drops"]]
    # ίδια κίνηση στο 1Χ2 δεν αρκεί
    h2 = {"pinnacle": book(x12([(200, 2.0)], [(200, 3.5)], [(200, 3.9), (90, 3.9), (10, 3.56)])),
          "stoiximan": book(x12([(200, 1.9)], [(200, 3.3)], [(200, 4.2)]))}
    s2 = [x for x in bot.analyze(FX, h2, NOW, MARKETS) if x["outcome"] == "103"]
    assert not s2 or bot.stars(s2[0]) == 1
    state = {}
    bot.save_diag(state, NOW)
    line = bot.diag_line(state, NOW)
    assert "γκολ 1" in line and "Κόπηκαν" in line, line
    print(line, "\n")


def test_steam_alerts():
    # Pinnacle πέφτει πολύ, η Stoiximan έχει ήδη πέσει (−1% από τη δίκαιη) → 📢
    hist = {"pinnacle": book(x12([(300, 2.30)], [(300, 3.30)], [(300, 3.40), (90, 3.40), (5, 2.90)])),
            "stoiximan": book(x12([(300, 2.20)], [(300, 3.10)], [(300, 3.08)]))}  # δίκαιη ≈ 3.14
    sig = [x for x in bot.analyze(FX, hist, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert not sig["values"] and sig["steam"] and bot.stars(sig) == 2
    sig["stake"] = bot.steam_stake({})
    msg = bot.format_signal(sig)
    assert "📢 ΜΠΑΙΝΟΥΝ ΜΕΓΑΛΑ ΛΕΦΤΑ" in msg and "χωρίς έξτρα αξία" in msg and sig["stake"] == 1.0, msg
    print(msg, "\n")
    state = {}
    bot.record_bet(state, sig)
    assert list(state["bets"].values())[0]["kind"] == "steam"
    # Stoiximan πολύ χαμηλά (−10%) → τίποτα
    hist["stoiximan"] = book(x12([(300, 2.2)], [(300, 3.1)], [(300, 2.70)]))
    assert not [x for x in bot.analyze(FX, hist, NOW, MARKETS) if x["outcome"] == "103"]
    # χωρίς μεγάλη πτώση → τίποτα
    calm = {"pinnacle": book(x12([(300, 2.3)], [(300, 3.3)], [(300, 3.0)])),
            "stoiximan": book(x12([(300, 2.2)], [(300, 3.1)], [(300, 2.98)]))}
    assert not bot.analyze(FX, calm, NOW, MARKETS)


def test_report_waits_for_pending_and_shows_them():
    base = {"market": "101", "outcome": "101", "match": "m", "pick": "p", "price": 2.0, "stars": 2,
            "start": "2026-10-10T19:00:00Z", "kind": "steam", "stake": 5}
    state = {"bets": {"a": {**base, "fixtureId": "a", "status": "settled", "result": "WIN"},
                      "b": {**base, "fixtureId": "b", "status": "open", "stake": 8.2}}}
    sent = []
    orig = bot.send_telegram
    bot.send_telegram = lambda m, reply_to=None: sent.append(m)
    try:
        t1035 = dt.datetime(2026, 10, 11, 7, 35, tzinfo=dt.timezone.utc)
        assert not bot.maybe_report(state, t1035)          # περιμένει το εκκρεμές
        t1235 = dt.datetime(2026, 10, 11, 9, 35, tzinfo=dt.timezone.utc)
        assert bot.maybe_report(state, t1235)              # μετά από 2 ώρες στέλνει έτσι κι αλλιώς
    finally:
        bot.send_telegram = orig
    r = sent[0]
    assert "⏳" in r and "8.2€" in r and "+5.00€" in r and "ποντάρισες 5€" in r, r
    print(r, "\n")


def test_tickets_candidates_build_and_replies():
    cat = {str(m["marketId"]): m for m in CATALOG}
    cat["10783"] = {"marketId": 10783, "marketName": "Corners - Over Under Full Time", "handicap": 9.5,
                    "period": "fulltime", "outcomes": [{"outcomeId": 10783, "outcomeName": "Over"},
                                                       {"outcomeId": 10784, "outcomeName": "Under"}]}
    state = {}
    fixtures = []
    for i in range(12):
        fx = {**FX, "fixtureId": f"T{i}", "startTime": (NOW + dt.timedelta(hours=2 + i % 5)).isoformat(),
              "participant1ShortName": f"Home{i}", "participant2ShortName": f"Away{i}"}
        fixtures.append(fx)
        p1 = 1.40 + 0.03 * i   # ποικιλία αποδόσεων ανά αγώνα
        p2 = round(1 / (1.04 - 1 / p1 - 1 / 3.6), 2)   # ρεαλιστικό περιθώριο ~4%
        hist = {"pinnacle": book({"101": {"101": [(300, p1 + 0.15), (10, p1)], "102": [(300, 3.6)], "103": [(300, p2)]},
                                  "1010": {"1010": [(300, 1.75), (20, 1.60)], "1011": [(300, 2.25)]},
                                  "10783": {"10783": [(300, 1.90)], "10784": [(300, 1.90)]}}),
                "stoiximan": book({"101": {"101": [(300, round(p1 * 1.03, 2))], "102": [(300, 3.4)], "103": [(300, p2)]},
                                   "1010": {"1010": [(300, 1.66)], "1011": [(300, 2.20)]},
                                   "10783": {"10783": [(300, 1.97)], "10784": [(300, 1.92)]}})}
        n = bot.collect_candidates(state, fx, hist, NOW, cat, MARKETS)
        assert n >= 2, (i, n)
    groups = {c["group"] for c in state["cands"]["T0"]}
    assert {"1x2", "goals", "corners"} <= groups, groups
    pool = sorted([c for v in state["cands"].values() for c in v], key=lambda c: -c["score"])
    for spec in C.TICKETS:
        legs = bot.build_ticket(pool, spec, set())
        assert legs, spec["name"]
        odds = 1.0
        for c in legs:
            odds *= c["price"]
        assert spec["min"] <= odds <= spec["max"], (spec["name"], odds)
        assert len({c["fid"] for c in legs}) == len(legs)          # ένα σημείο ανά αγώνα
        assert {c["group"] for c in legs} <= set(spec["groups"])
        assert all(c["price"] <= spec.get("leg_max", 99) for c in legs), spec["name"]
        for k, cap in spec.get("max_kind", {}).items():
            assert sum(1 for c in legs if k == c["group"] or k in bot.norm(c["label"])) <= cap, (spec["name"], k)
    sent = []
    orig = bot.send_telegram
    ids = iter(range(500, 600))
    bot.send_telegram = lambda m, reply_to=None: (sent.append(m), next(ids))[1]
    try:
        noon = dt.datetime(2026, 10, 10, 9, 5, tzinfo=dt.timezone.utc)   # 12:05 Ελλάδας
        st2 = {"cands": {k: [{**c, "start": (noon + dt.timedelta(hours=3)).isoformat()} for c in v]
                         for k, v in state["cands"].items()}}
        assert bot.maybe_send_tickets(st2, noon) == len(C.TICKETS)
        assert bot.maybe_send_tickets(st2, noon + dt.timedelta(minutes=5)) == 0   # μία φορά τη μέρα
    finally:
        bot.send_telegram = orig
    assert "ΔΕΛΤΙΑ ΗΜΕΡΑΣ" in sent[0] and "Πιθανότητα <b>" in sent[1]
    print(sent[2], "\n")
    tk = list(st2["tickets"].values())[1]
    mid = tk["msg_ids"][0]
    upd = {"ok": True, "result": [
        {"update_id": 1, "message": {"message_id": 1, "chat": {"id": C.TELEGRAM_CHAT_ID or "123"}, "text": "5",
                                     "reply_to_message": {"message_id": mid}}},
        {"update_id": 2, "message": {"message_id": 2, "chat": {"id": C.TELEGRAM_CHAT_ID or "123"}, "text": "✅",
                                     "reply_to_message": {"message_id": mid}}}]}
    C.TELEGRAM_CHAT_ID = C.TELEGRAM_CHAT_ID or "123"
    og, osend = bot.requests.get, bot.send_telegram
    bot.requests.get = lambda *a, **k: type("R", (), {"ok": True, "json": lambda self: upd})()
    bot.send_telegram = lambda m, reply_to=None: None
    try:
        assert bot.process_replies(st2) == 2
    finally:
        bot.requests.get, bot.send_telegram = og, osend
    assert tk["stake"] == 5 and tk["result"] == "WIN"
    assert abs(bot.bankroll(st2) - (C.BANKROLL + 5 * (tk["odds"] - 1))) < 0.02
    rep = bot.build_report(st2, dt.datetime(2026, 10, 11, 8, 0, tzinfo=dt.timezone.utc))
    assert "🎟️ <b>Δελτία</b>" in rep and "Δελτία:" in rep, rep


def test_no_reply_means_not_played():
    no_bf = {k: v for k, v in HIST.items() if k != "betfair-ex"}
    sig = [x for x in bot.analyze(FX, no_bf, NOW, MARKETS) if x["outcome"] == "103"][0]
    sig["stake"] = 7.0
    state = {}
    bot.record_bet(state, sig, 321)
    b = list(state["bets"].values())[0]
    assert b["stake"] == 0 and b["suggested"] == 7.0 and not b["replied"]
    b.update(status="settled", result="WIN")
    assert bot.bet_pnl(b) == 0 and bot.bankroll(state) == C.BANKROLL      # δεν παίχτηκε
    assert abs(bot.virtual_pnl(b) - 7 * (b["price"] - 1)) < 0.01         # αλλά μετράει στο "αν έπαιζες"
    rep = bot.build_report(state, dt.datetime(2026, 10, 11, 8, 0, tzinfo=dt.timezone.utc))
    assert "▫️" in rep and "θα ήταν" in rep and "Όλες οι ειδοποιήσεις" in rep, rep


def test_dedup():
    state = {"alerts": {}}
    s = [x for x in bot.analyze(FX, HIST, NOW, MARKETS) if x["outcome"] == "103"][0]
    assert bot.should_alert(state, s) is True
    assert bot.should_alert(state, s) is False  # ίδιο σήμα → όχι ξανά


def test_quiet_market():
    quiet = {"pinnacle": book(x12([(300, 2.30)], [(300, 3.30)], [(300, 3.40)])),
             "stoiximan": book(x12([(300, 2.20)], [(300, 3.15)], [(300, 3.20)]))}
    assert bot.analyze(FX, quiet, NOW, MARKETS) == []


def test_league_filter():
    def L(cat, name, tid=1):
        return bot.league_ok({"tournamentId": tid, "categorySlug": cat, "categoryName": cat,
                              "tournamentName": name})
    ok = [("greece", "Super League"), ("greece", "Super League 2"), ("england", "Championship"),
          ("england", "League One"), ("scotland", "Premiership"), ("scotland", "League One"),
          ("switzerland", "Challenge League"), ("switzerland", "Promotion League"),
          ("denmark", "Superliga"), ("denmark", "1st Division"), ("denmark", "2nd Division, Group 1"),
          ("germany", "3. Liga"), ("italy", "Serie C, Group A"), ("turkey", "Trendyol Süper Lig"),
          ("brazil", "Brasileirão Série B"), ("europe", "UEFA Champions League"),
          ("international-clubs", "UEFA Conference League"), ("poland", "II Liga")]
    bad = [("england", "League Two"), ("england", "Premier League 2"), ("france", "National 2"),
           ("italy", "Serie D, Group A"), ("germany", "Frauen Bundesliga"), ("poland", "III Liga"),
           ("greece", "Super League U19"), ("england", "FA Cup"), ("kenya", "Premier League"),
           ("europe", "UEFA Women's Champions League"), ("spain", "Segunda Federación")]
    for c, n in ok:
        assert L(c, n), f"έπρεπε να περάσει: {c} {n}"
    for c, n in bad:
        assert not L(c, n), f"έπρεπε να κοπεί: {c} {n}"


def test_rotation_and_live_first():
    def fx(i, h):
        return {"fixtureId": f"f{i}", "tournamentId": 1, "categorySlug": "england",
                "tournamentName": "Championship",
                "startTime": (NOW + dt.timedelta(hours=h)).isoformat()}
    state = {"fixtures": [fx(1, 1), fx(2, 4), fx(3, 5), fx(4, -0.5), fx(5, -3), fx(6, 8)],
             "checked": {"f2": "2026-10-10T11:50:00Z"}}  # ο f2 ελέγχθηκε πριν 10′ (χρειάζεται κάθε 20′)
    order = [f["fixtureId"] for f in bot.select_fixtures(state, NOW)]
    assert order == ["f1", "f3", "f6", "f2"], order   # χωρίς live· ο f2 στο τέλος (δεν "χρωστάει")
    C.MIN_STARS = 1
    try:
        order = [f["fixtureId"] for f in bot.select_fixtures(state, NOW)]
        assert order[0] == "f4", order
    finally:
        C.MIN_STARS = 2


def test_priority_group_rotates_when_crowded():
    fxs = [{"fixtureId": f"p{i}", "tournamentId": 1, "categorySlug": "england",
            "tournamentName": "Championship",
            "startTime": (NOW + dt.timedelta(minutes=70 + i)).isoformat()} for i in range(60)]
    state = {"fixtures": fxs, "checked": {}}
    C.MAX_FIXTURES = 40
    first = [f["fixtureId"] for f in bot.select_fixtures(state, NOW)]
    for fid in first:
        state["checked"][fid] = bot.iso(NOW)
    second = [f["fixtureId"] for f in bot.select_fixtures(state, NOW + dt.timedelta(minutes=5))]
    assert set(first) | set(second) == {f["fixtureId"] for f in fxs}
    assert second[:20] == [f"p{i}" for i in range(40, 60)]


def test_tiers_urgent_every_round():
    near = {"fixtureId": "near", "tournamentId": 1, "categorySlug": "england", "tournamentName": "Championship",
            "startTime": (NOW + dt.timedelta(minutes=40)).isoformat()}
    far = [{"fixtureId": f"far{i}", "tournamentId": 1, "categorySlug": "england",
            "tournamentName": "Championship",
            "startTime": (NOW + dt.timedelta(hours=4, minutes=i)).isoformat()} for i in range(60)]
    state = {"fixtures": far + [near], "checked": {"near": bot.iso(NOW - dt.timedelta(minutes=5))}}
    C.MAX_FIXTURES = 40
    sel = [f["fixtureId"] for f in bot.select_fixtures(state, NOW)]
    assert sel[0] == "near"   # ο κοντινός (σε 40′) ελέγχεται σε κάθε γύρο, πριν από τους μακρινούς
    assert bot.check_interval_min(bot.parse_ts(near["startTime"]), NOW) == 5
    assert bot.check_interval_min(NOW + dt.timedelta(hours=2), NOW) == 10
    assert bot.check_interval_min(NOW + dt.timedelta(hours=5), NOW) == 20


def test_all_books_required():
    assert bot.has_all_books(HIST, MARKETS)
    missing = {k: v for k, v in HIST.items() if k != "pamestoixima-gr"}
    assert not bot.has_all_books(missing, MARKETS)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"✓ {name}")
    print("Όλα τα τεστ πέρασαν.")
