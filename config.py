"""
Ρυθμίσεις του bot. Άλλαξε ελεύθερα τις τιμές εδώ.
Τα μυστικά (κλειδιά) ΔΕΝ μπαίνουν εδώ — μπαίνουν στα GitHub Secrets.
"""
import os

# ---------- Μυστικά (από GitHub Secrets / μεταβλητές περιβάλλοντος) ----------
ODDSPAPI_KEY = os.environ.get("ODDSPAPI_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---------- Bookmakers ----------
# "Sharp" = εκεί που κινούνται πρώτα τα μεγάλα/έξυπνα λεφτά.
SHARP_BOOK = "pinnacle"
USE_BETFAIR = True            # Betfair Exchange (έξτρα κλήση ανά αγώνα)

# Ελληνικοί bookmakers που συγκρίνουμε (ΜΕΧΡΙ 2 — όριο του API).
# Διαθέσιμοι: stoiximan, pamestoixima-gr, bet365-gr, vistabet, interwetten, bwin, netbet
GREEK_BOOKS = ["stoiximan", "pamestoixima-gr"]

BOOK_NAMES = {
    "pinnacle": "Pinnacle",
    "betfair-ex": "Betfair",
    "stoiximan": "Stoiximan",
    "pamestoixima-gr": "Pamestoixima",
    "bet365-gr": "Bet365",
    "vistabet": "Vistabet",
    "interwetten": "Interwetten",
    "bwin": "Bwin",
    "netbet": "NetBet",
}

# ---------- Αγορές ----------
# Το bot βρίσκει μόνο του τους κωδικούς τους από τον κατάλογο του API.
# kind: "1x2" | "totals" (Over/Under) | "correct_score"
# period: "full" (τελικό) | "half1" (1ο ημίχρονο)
# lines: ποια όρια γκολ (μόνο για totals). max_odds: πάνω όριο απόδοσης για αυτή την αγορά.
MARKETS = [
    {"name": "Τελικό αποτέλεσμα 1Χ2", "kind": "1x2", "period": "full"},
    {"name": "Over/Under 2.5", "kind": "totals", "period": "full", "lines": [2.5]},
    {"name": "Over/Under Ημιχρόνου", "kind": "totals", "period": "half1", "lines": [0.5, 1.5]},
    {"name": "Ακριβές σκορ", "kind": "correct_score", "period": "full", "max_odds": 15.0},
]
MARKETS_REFRESH_DAYS = 7      # κάθε πόσο ξαναδιαβάζει τον κατάλογο αγορών (1 αίτημα)

# ---------- Πότε θεωρείται "αξίζει" (προαγωνιστικά) ----------
DROP_WINDOW_MIN = 60          # κοιτάμε την πτώση στα τελευταία Χ λεπτά
DROP_PCT = 12.0               # πτώση ≥ 12% μέσα στο παράθυρο → ειδοποίηση
DROP_FROM_OPEN_PCT = 20.0     # ή πτώση ≥ 20% από την αρχική απόδοση
VALUE_EDGE_PCT = 5.0          # ελληνικός δίνει ≥ 5% πάνω από τη "δίκαιη" απόδοση
MIN_ODDS = 1.40               # αγνοούμε πολύ χαμηλές αποδόσεις
MAX_ODDS = 8.0                # και πολύ υψηλές (θόρυβος)

# ---------- Live αγώνες ----------
# Στα live οι αποδόσεις πέφτουν ΦΥΣΙΟΛΟΓΙΚΑ με τον χρόνο και τα γκολ, όχι λόγω λεφτών.
# Γι' αυτό στα live στέλνει μόνο ευκαιρίες αξίας (ελληνικός πάνω από τη δίκαιη), με αυστηρότερο όριο.
LIVE_ENABLED = True
LIVE_MAX_MINUTES = 115        # αγώνας θεωρείται live μέχρι Χ λεπτά μετά την έναρξη
LIVE_VALUE_EDGE_PCT = 7.0     # αυστηρότερο όριο αξίας στα live
LIVE_DROPS = False            # True = στέλνει και πτώσεις στα live (πολύς θόρυβος)
LIVE_MAX_PRICE_AGE_MIN = 5    # αγνοεί τιμές που δεν έχουν ανανεωθεί τα τελευταία Χ λεπτά

# Ξαναστέλνει για το ίδιο σημείο μόνο αν δυναμώσει το σήμα κατά τόσο:
REALERT_DROP_STEP = 4.0       # +4 μονάδες % πτώσης
REALERT_EDGE_STEP = 2.0       # +2 μονάδες % αξίας

# ---------- Ποιους αγώνες παρακολουθούμε ----------
LOOKAHEAD_HOURS = 6           # αγώνες που ξεκινούν μέσα στις επόμενες Χ ώρες
MAX_FIXTURES = 60             # μέγιστος αριθμός αγώνων ανά γύρο (≈11 δευτ. ο καθένας)
PRIORITY_HOURS = 2            # αγώνες που ξεκινούν μέσα σε Χ ώρες ελέγχονται πρώτοι, κάθε γύρο
FIXTURE_REFRESH_HOURS = 6     # κάθε πόσο ανανεώνεται η λίστα αγώνων (χρεώνεται 1 αίτημα)

# Λίγκες που παρακολουθούμε: χώρα → ονόματα λιγκών (1η, 2η, 3η κατηγορία).
# Τα ονόματα είναι "μοτίβα" (regex) που ψάχνονται μέσα στο όνομα της λίγκας, χωρίς τόνους/κεφαλαία.
# ^ = αρχή ονόματος, $ = τέλος. Βάλε # μπροστά σε μια γραμμή για να βγάλεις τη χώρα.
# Έλεγχος ποιες λίγκες πιάνει: Run workflow → mode "leagues" (✅ = παρακολουθείται).
COUNTRY_LEAGUES = {
    # χώρα (όπως τη γράφει το API, κάποιες με εναλλακτικά ονόματα): [1η, 2η, 3η]
    ("england",):                  [r"^premier league$", r"^championship$", r"^league one$"],
    ("spain",):                    [r"^laliga$", r"laliga 2|hypermotion", r"primera (federacion|rfef)"],
    ("italy",):                    [r"^serie a$", r"^serie b$", r"^serie c"],
    ("germany",):                  [r"^bundesliga$", r"^2\. bundesliga$", r"^3\. liga$"],
    ("france",):                   [r"^ligue 1$", r"^ligue 2$", r"^national$"],
    ("greece",):                   [r"super league", r"gamma ethniki"],
    ("netherlands",):              [r"eredivisie", r"eerste divisie", r"tweede divisie"],
    ("portugal",):                 [r"^liga portugal", r"^liga 3"],
    ("turkey", "turkiye"):         [r"super lig", r"^1\. lig", r"^2\. lig"],
    ("belgium",):                  [r"pro league", r"national (division )?1"],
    ("scotland",):                 [r"^premiership$", r"^championship$", r"^league one$"],
    ("switzerland",):              [r"^super league$", r"^challenge league$", r"^promotion league$"],
    ("denmark",):                  [r"superliga", r"^(1st|1\.) division$", r"^(2nd|2\.) division"],
    ("austria",):                  [r"^bundesliga$", r"^2\. liga$", r"^regionalliga"],
    ("norway",):                   [r"eliteserien", r"obos|^1\. divisjon$", r"postnord|^2\. divisjon"],
    ("sweden",):                   [r"allsvenskan", r"superettan", r"^ettan"],
    ("poland",):                   [r"ekstraklasa", r"\bi liga$|^1\. liga$", r"\bii liga$|^2\. liga$"],
    ("czech-republic", "czechia", "czech republic"): [r"chance liga|^1\. liga$|first league", r"^2\. liga$|fnl|national football league"],
    ("croatia",):                  [r"hnl|supersport", r"prva nl", r"druga nl"],
    ("romania",):                  [r"superliga|^liga 1$", r"^liga 2$", r"^liga 3"],
    ("serbia",):                   [r"super ?liga", r"prva liga"],
    ("cyprus",):                   [r"1st division|first division|^1\. division", r"2nd division|second division"],
    ("saudi-arabia", "saudi arabia"): [r"pro league", r"first division|division 1"],
    ("usa",):                      [r"^mls$|major league soccer", r"usl championship", r"usl league one"],
    ("brazil",):                   [r"serie a$", r"serie b$", r"serie c$"],
    ("argentina",):                [r"liga profesional|primera lpf", r"primera nacional", r"primera b metropolitana"],
}

# Ευρωπαϊκά κύπελλα (ψάχνεται στο όνομα, σε οποιαδήποτε χώρα/κατηγορία)
CUPS = [r"champions league", r"europa league", r"conference league"]

# Έξτρα λίγκες με το ID τους (από το mode "leagues"), π.χ. {44: "Κάτι άλλο"}
EXTRA_LEAGUE_IDS = {}

# Παρακολουθούμε αγώνα ΜΟΝΟ αν έχει αποδόσεις στο Pinnacle ΚΑΙ σε όλους τους GREEK_BOOKS.
REQUIRE_ALL_BOOKS = True

# Διοργανώσεις που αποκλείονται πάντα
EXCLUDE_KEYWORDS = ["u17", "u18", "u19", "u20", "u21", "u23", "women", "woman", "frauen",
                    "youth", "junior", "reserve", "amateur", "friendly", "premier league 2",
                    "play-off", "playoff", " cup"]

MAX_RUNTIME_SEC = 9 * 60      # κάθε γύρος σταματάει στα 9′ για να προλαβαίνει τον επόμενο (κάθε 10′)

# ---------- Ήσυχες ώρες (ώρα Ελλάδας) ----------
# Αυτές τις ώρες στέλνει ΜΟΝΟ σοβαρές περιπτώσεις. Τα υπόλοιπα σήματα, αν ισχύουν ακόμα,
# έρχονται όταν τελειώσουν οι ήσυχες ώρες. QUIET_START = QUIET_END → χωρίς ήσυχες ώρες.
QUIET_START = 2               # από τις 02:00
QUIET_END = 11                # έως τις 11:00
# "Σοβαρή" = πτώση + αξία μαζί (🔥), ή πτώση ≥ Χ%, ή αξία ≥ Χ%
SERIOUS_DROP_PCT = 25.0
SERIOUS_EDGE_PCT = 10.0
