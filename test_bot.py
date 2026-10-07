"""Τεστ λογικής με ψεύτικα δεδομένα (δεν χρειάζεται internet). Τρέξε: python test_bot.py"""
import datetime as dt

import bot

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
MARKETS = bot.resolve_markets(CATALOG)


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
    assert names == {"101": "Τελικό αποτέλεσμα 1Χ2", "1010": "Over/Under 2.5",
                     "1020": "Over/Under Ημιχρόνου (0.5)", "1022": "Over/Under Ημιχρόνου (1.5)",
                     "1100": "Ακριβές σκορ"}, names  # όχι BTTS, όχι 3.5, όχι κόρνερ


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
    assert bot.is_serious(big)
    big["quiet"] = True
    assert bot.format_signal(big).startswith("<b>🚨 ΣΟΒΑΡΟ")


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
             "checked": {"f2": "2026-10-10T11:50:00Z"}}
    order = [f["fixtureId"] for f in bot.select_fixtures(state, NOW)]
    # live πρώτα, μετά όσοι ξεκινούν σύντομα, μετά εκ περιτροπής·
    # ο f5 (πριν 3 ώρες) έχει τελειώσει, ο f6 (σε 8 ώρες) είναι εκτός παραθύρου 6 ωρών
    assert order == ["f4", "f1", "f3", "f2"], order


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
