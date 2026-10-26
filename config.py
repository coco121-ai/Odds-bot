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
# Betfair Exchange: στο δωρεάν πλάνο θέλει 1 αίτημα ανά αποτέλεσμα (πολύ αργό) → κλειστό.
USE_BETFAIR = False

# ---------- Επιβεβαίωση από πολλές πηγές ----------
# Όταν η Stoiximan δίνει αξία, το bot ελέγχει αν η απόδοση πέφτει και σε άλλες "έξυπνες" πηγές.
# Pinnacle (πάντα) + Betfair Exchange + ασιατικοί sharp bookmakers (SBOBet, Singbet).
# Τα αιτήματα ιστορικού αποδόσεων ΔΕΝ χρεώνονται στο μηνιαίο όριο.
BETFAIR_CONFIRM = True
BETFAIR_MIN_LIQUIDITY = 50    # αγνοεί τιμές Betfair με λιγότερα από €Χ διαθέσιμα (θόρυβος)
CONFIRM_BOOKS = ["sbobet", "singbet"]   # μέχρι 3
# Αν μία πηγή έχει μεγάλη πτώση (DROP_PCT), οι άλλες μετράνε ως επιβεβαίωση με μικρότερη πτώση:
CONFIRM_DROP_PCT = 6.0        # ≥ 6% στο ίδιο παράθυρο
CONFIRM_DROP_FROM_OPEN_PCT = 10.0
# Μια μεγάλη πτώση στο Pinnacle μετράει ως "μεγάλα λεφτά" μόνο αν η αγορά δέχεται τουλάχιστον τόσα €
# (σε μικρές λίγκες λίγα λεφτά αρκούν για να κινηθεί η απόδοση).
MIN_PINNACLE_LIMIT = 1000

# Αγορές γκολ (Over/Under): οι αποδόσεις κινούνται λιγότερο → χαλαρότερα όρια
TOTALS_DROP_PCT = 8.0                 # (1Χ2: 12%)
TOTALS_DROP_FROM_OPEN_PCT = 13.0      # (1Χ2: 20%)
TOTALS_CONFIRM_DROP_PCT = 5.0         # (1Χ2: 6%)
TOTALS_CONFIRM_DROP_FROM_OPEN_PCT = 8.0   # (1Χ2: 10%)
TOTALS_MIN_PINNACLE_LIMIT = 500       # (1Χ2: €1.000) — το Pinnacle δέχεται μικρότερα ποσά στα γκολ

# ---------- Ποιες ειδοποιήσεις στέλνονται ----------
# ⭐ = μόνο αξία · ⭐⭐ = αξία + μεγάλη πτώση σε 1 πηγή · ⭐⭐⭐ = αξία + πτώση σε 2+ πηγές
MIN_STARS = 2

# 📢 "Μπαίνουν λεφτά": μεγάλη πτώση στα έξυπνα λεφτά, ενώ η Stoiximan έχει ήδη προσαρμοστεί
# (δεν δίνει έξτρα αξία, αλλά ούτε είναι πολύ χαμηλότερα από τη δίκαιη). Μετράνε χωριστά στο PnL.
STEAM_ALERTS = True
STEAM_MIN_EDGE_PCT = -2.0     # η Stoiximan έως 2% κάτω από τη δίκαιη (κάτω από −2%: 40% επιτυχία, −30%)

# ---------- Στατιστικά ομάδων (football-data.co.uk, δωρεάν) ----------
# Αγγλία 1–5, Σκωτία 1–4, Γερμανία/Ιταλία/Ισπανία/Γαλλία 1–2, Ολλανδία, Βέλγιο, Πορτογαλία, Τουρκία, Ελλάδα.
STATS_ENABLED = True
STATS_REFRESH_HOURS = 12      # κάθε πόσο ξανακατεβάζει τα αποτελέσματα μιας λίγκας
STATS_KEEP_MATCHES = 20       # πόσους πρόσφατους αγώνες κρατάει ανά ομάδα
STATS_LAST_MATCHES = 10       # από πόσους τελευταίους (εντός ή εκτός) υπολογίζει
STATS_MIN_MATCHES = 6         # ελάχιστοι αγώνες (γηπεδούχου εντός + φιλοξενούμενου εκτός) για πρόβλεψη
STATS_SHRINK = 4              # "τράβηγμα" προς τον μέσο όρο της λίγκας όταν υπάρχουν λίγοι αγώνες
STATS_CORNER_DISPERSION = 1.3 # τα κόρνερ έχουν μεγαλύτερη διασπορά από τα γκολ
# Over/Under γκολ: στέλνεται μόνο αν τα στατιστικά δίνουν ≥ Χ% στην ίδια επιλογή (αν υπάρχουν στατιστικά)
STATS_FILTER_OVERS = True
STATS_MIN_MODEL_PROB = 50
# 🚩 Κόρνερ: ειδοποίηση όταν συμφωνούν στατιστικά ΚΑΙ αγορά
CORNERS_ALERTS = True
CORNERS_MIN_MODEL_PROB = 55       # τα στατιστικά δίνουν ≥ Χ%
CORNERS_MIN_MODEL_EDGE_PCT = 5    # και η απόδοση της Stoiximan δίνει ≥ Χ% αξία κατά τα στατιστικά
CORNERS_MIN_PIN_EDGE_PCT = 0      # και η Stoiximan δεν είναι κάτω από τη δίκαιη του Pinnacle
CORNERS_MIN_MARKET_PROB = 50      # και κατά το Pinnacle η πιθανότητα είναι ≥ Χ%
CORNERS_MIN_PIN_LIMIT = 300       # το Pinnacle δέχεται ≥ €Χ στα κόρνερ (αν το δίνει)
CORNERS_MAX_PER_DAY = 3
# Αν μια ομάδα δεν αντιστοιχίζεται σωστά: "όνομα στο OddsPapi": "όνομα στο football-data"
TEAM_ALIASES = {}

# Φίλτρα ποιότητας (από τα αποτελέσματα των πρώτων εβδομάδων)
ALERT_MIN_PIN_LIMIT = 2000    # μόνο όταν το Pinnacle δέχεται ≥ €Χ σε αυτή την επιλογή (μεγάλη, αξιόπιστη αγορά)
ALERT_MAX_HOURS_BEFORE = 6    # ειδοποιήσεις μόνο τις τελευταίες Χ ώρες πριν τη σέντρα
STEAM_STAKE_PCT = 1           # προτεινόμενο ποντάρισμα: 1% της κάσας

# Ελληνικοί bookmakers που συγκρίνουμε (ΜΕΧΡΙ 2 — όριο του API).
# Αν ένα όνομα είναι λάθος, το bot βρίσκει μόνο του το σωστό από τη λίστα του API.
GREEK_BOOKS = ["stoiximan"]

BOOK_NAMES = {
    "pinnacle": "Pinnacle",
    "betfair-ex": "Betfair",
    "stoiximan": "Stoiximan",
    "pamestoixima-gr": "Pamestoixima",
    "pamestoixima.gr": "Pamestoixima",
    "pamestoixima": "Pamestoixima",
    "bet365-gr": "Bet365",
    "vistabet": "Vistabet",
    "interwetten": "Interwetten",
    "bwin": "Bwin",
    "netbet": "NetBet",
    "sbobet": "SBOBet",
    "singbet": "Singbet",
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
    # Ακριβές σκορ: βγήκε, οι αποδόσεις του είναι πάντα πολύ ψηλές (μικρή πιθανότητα)
    # {"name": "Ακριβές σκορ", "kind": "correct_score", "period": "full", "max_odds": 15.0},
]
MARKETS_REFRESH_DAYS = 7      # κάθε πόσο ξαναδιαβάζει τον κατάλογο αγορών (1 αίτημα)

# ---------- Πότε θεωρείται "αξίζει" (προαγωνιστικά) ----------
DROP_WINDOW_MIN = 60          # κοιτάμε την πτώση στα τελευταία Χ λεπτά
DROP_PCT = 12.0               # πτώση ≥ 12% μέσα στο παράθυρο → ειδοποίηση
DROP_FROM_OPEN_PCT = 20.0     # ή πτώση ≥ 20% από την αρχική απόδοση
VALUE_EDGE_PCT = 2.5          # Stoiximan ≥ 2.5% πάνω από τη "δίκαιη" απόδοση (μαζί με μεγάλη πτώση)
# Στέλνει ΜΟΝΟ όταν η Stoiximan δίνει αξία. True = στέλνει και σκέτες πτώσεις στο Pinnacle.
SEND_DROPS_WITHOUT_VALUE = False
MIN_ODDS = 1.40               # αγνοούμε πολύ χαμηλές αποδόσεις (πιθανότητα > ~70%)
MAX_ODDS = 2.50               # μόνο "σίγουρες" επιλογές: πιθανότητα ~40% και πάνω
MIN_PROB_PCT = 52             # ειδοποίηση μόνο αν η πιθανότητα (από τη δίκαιη απόδοση) είναι ≥ Χ% → 🟢

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
LOOKAHEAD_HOURS = 24          # αγώνες που ξεκινούν μέσα στις επόμενες Χ ώρες
MAX_FIXTURES = 40             # μέγιστος αριθμός αγώνων ανά γύρο (~5 δευτ. ο καθένας)
PRIORITY_HOURS = 3            # αγώνες που ξεκινούν μέσα σε Χ ώρες ελέγχονται πρώτοι, κάθε γύρο
# Κάθε πόσα λεπτά ελέγχεται ένας αγώνας ανάλογα με το πόσο απέχει η σέντρα: (έως Χ ώρες, κάθε Υ λεπτά)
CHECK_TIERS = [
    (1, 5),       # τελευταία 1 ώρα → σε κάθε γύρο
    (3, 10),      # 1–3 ώρες πριν → κάθε 10′
    (6, 20),      # 3–6 ώρες πριν → κάθε 20′
    (12, 60),     # 6–12 ώρες πριν → κάθε 60′ (για τα δελτία ημέρας)
    (24, 120),    # 12–24 ώρες πριν → κάθε 2 ώρες (για το βραδινό δελτίο)
]
FIXTURE_REFRESH_HOURS = 12    # κάθε πόσο ανανεώνεται η λίστα αγώνων (χρεώνεται 1 αίτημα)

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

MAX_RUNTIME_SEC = 4 * 60 + 15 # κάθε γύρος σταματάει στα ~4′ για να προλαβαίνει τον επόμενο (κάθε 5′)

# ---------- Ήσυχες ώρες (ώρα Ελλάδας) ----------
# Αυτές τις ώρες στέλνει ΜΟΝΟ σοβαρές περιπτώσεις. Τα υπόλοιπα σήματα, αν ισχύουν ακόμα,
# έρχονται όταν τελειώσουν οι ήσυχες ώρες. QUIET_START = QUIET_END → χωρίς ήσυχες ώρες.
QUIET_START = 2               # από τις 02:00
QUIET_END = 11                # έως τις 11:00
# "Σοβαρή" = πτώση + αξία μαζί (🔥), ή πτώση ≥ Χ%, ή αξία ≥ Χ%
SERIOUS_DROP_PCT = 25.0
SERIOUS_EDGE_PCT = 10.0

# ---------- Στατιστικά / PnL ----------
# Κάθε ειδοποίηση μετράει ως εικονικό στοίχημα STAKE € στην απόδοση της Stoiximan.
# Μετά τον αγώνα το bot βρίσκει το αποτέλεσμα και κάθε βράδυ στέλνει απολογισμό.
STAKE = 2                     # € μόνο αν δεν μπορεί να υπολογιστεί προτεινόμενο ποντάρισμα

# ---------- Ποντάρισμα (Kelly 25%) ----------
# Το ποσό κάθε ειδοποίησης βγαίνει από την κάσα και το πόσο δυνατή είναι η ευκαιρία.
# Η κάσα ενημερώνεται μόνη της με τα κέρδη/ζημιές.
BANKROLL = 500                # € αρχική κάσα
KELLY_FRACTION = 0.25         # 25% του Kelly (λιγότερες διακυμάνσεις)
MAX_STAKE_PCT = 5             # ποτέ πάνω από 5% της κάσας σε ένα ματς
MIN_STAKE = 1                 # € ελάχιστο ποντάρισμα
REPORT_TIME = "10:30"         # ώρα Ελλάδας: απολογισμός της ΠΡΟΗΓΟΥΜΕΝΗΣ μέρας (όλα τα ματς έχουν κλείσει)
SETTLE_AFTER_HOURS = 3        # ψάχνει αποτέλεσμα Χ ώρες μετά την έναρξη
SETTLE_RETRY_HOURS = 2        # αν δεν βρεθεί, ξαναδοκιμάζει κάθε Χ ώρες
SETTLE_MAX_TRIES = 4          # μετά από τόσες αποτυχίες → "χωρίς αποτέλεσμα"
SETTLE_MAX_PER_DAY = 12       # ανώτατο ανά μέρα· το bot μοιράζει μόνο του ό,τι μένει από τα 250/μήνα
QUOTA_RESERVE = 25            # αφήνει πάντα τόσα αιτήματα για τη λίστα αγώνων
KEEP_BETS_DAYS = 120          # για πόσες μέρες κρατάει το ιστορικό
CLV_MAX_PER_RUN = 5           # πόσους αγώνες ελέγχει για CLV ανά γύρο (δωρεάν αιτήματα)

# Μηδενισμός στατιστικών: άλλαξε αυτή την τιμή (π.χ. σε σημερινή ημερομηνία) για να ξεκινήσει
# από την αρχή το PnL. Το bot σβήνει τα παλιά στοιχήματα στον επόμενο γύρο.
STATS_RESET = "restart-1"

# ---------- Δελτία ημέρας ----------
# Κάθε μέρα στις TICKETS_TIME στέλνει δελτία (συνδυασμούς από διαφορετικά ματς) με τις πραγματικές
# αποδόσεις της Stoiximan. Τα ποσά τα αποφασίζεις εσύ (απάντηση με ποσό, και μετά ✅ ή ❌).
TICKETS_ENABLED = True
TICKETS_TIME = "12:00"            # ώρα Ελλάδας
TICKET_WINDOW_HOURS = 12          # αγώνες που ξεκινούν μέσα στις επόμενες Χ ώρες
TICKET_MIN_MINUTES_BEFORE = 20    # όχι αγώνες που ξεκινούν σε λιγότερο από Χ λεπτά
TICKET_MIN_EDGE_PCT = -4.0        # η Stoiximan έως 4% κάτω από τη δίκαιη απόδοση
TICKET_LEG_MIN_ODDS = 1.30
TICKET_LEG_MAX_ODDS = 3.20
TICKET_MAX_LEGS = 10
TICKET_POOL_SIZE = 40             # από πόσες καλύτερες επιλογές διαλέγει
TICKET_BEAM = 300                 # εύρος αναζήτησης συνδυασμών
TICKET_DROP_WEIGHT = 0.3          # πόσο μετράει το "μπαίνουν λεφτά" στην επιλογή
TICKET_MONEY_DROP_PCT = 5.0       # 💸 όταν η απόδοση στο Pinnacle έχει πέσει ≥ Χ% από την αρχή
ALL_GROUPS = ["1x2", "goals", "btts", "corners", "cards"]
TICKET_AUTO_SETTLE = True         # βρίσκει μόνο του αν βγήκε το δελτίο και σου το λέει
TICKETS = [
    # Ημέρας (TICKETS_TIME, αγώνες των επόμενων TICKET_WINDOW_HOURS ωρών)
    # 1) x10–30: «σίγουρα» σημεία έως 1.70, κυρίως Over (γκολ / ημίχρονο), έως 2 σημεία 1Χ2, έως 1 Under
    {"name": "Δελτίο x10–30 · Over (έως 1.70)", "target": 15, "min": 10, "max": 30,
     "groups": ["goals", "1x2"], "leg_max": 1.70,
     "bonus": {"over": 3.0}, "max_kind": {"1x2": 2, "under": 1}},
    # 2) x80–100: από όλα — 1Χ2, γκολ, γκολ-γκολ, και το πολύ 1 κόρνερ και 1 κάρτες
    {"name": "Δελτίο x80–100 · από όλα", "target": 90, "min": 80, "max": 100, "groups": ALL_GROUPS,
     "max_kind": {"corners": 1, "cards": 1}},
    # Βραδινό: στις 23:45, αγώνες μέχρι το τέλος της επόμενης μέρας, απόδοση 20–30
    {"name": "Βραδινό x20–30", "time": "23:45", "window": 24, "target": 25, "min": 20, "max": 30,
     "groups": ["goals", "1x2", "btts"], "leg_max": 2.20,
     "bonus": {"over": 1.5}, "max_kind": {"1x2": 3, "under": 1}},
]
