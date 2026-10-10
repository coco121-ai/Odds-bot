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

# ---------- Ποιες ειδοποιήσεις στέλνονται ----------
# ⭐ = μόνο αξία · ⭐⭐ = αξία + μεγάλη πτώση σε 1 πηγή · ⭐⭐⭐ = αξία + πτώση σε 2+ πηγές
MIN_STARS = 2

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
VALUE_EDGE_PCT = 5.0          # ελληνικός δίνει ≥ 5% πάνω από τη "δίκαιη" απόδοση
# Στέλνει ΜΟΝΟ όταν η Stoiximan δίνει αξία. True = στέλνει και σκέτες πτώσεις στο Pinnacle.
SEND_DROPS_WITHOUT_VALUE = False
MIN_ODDS = 1.40               # αγνοούμε πολύ χαμηλές αποδόσεις (πιθανότητα > ~70%)
MAX_ODDS = 2.50               # μόνο "σίγουρες" επιλογές: πιθανότητα ~40% και πάνω

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
MAX_FIXTURES = 40             # μέγιστος αριθμός αγώνων ανά γύρο (~5 δευτ. ο καθένας)
PRIORITY_HOURS = 3            # αγώνες που ξεκινούν μέσα σε Χ ώρες ελέγχονται πρώτοι, κάθε γύρο
FIXTURE_REFRESH_HOURS = 8     # κάθε πόσο ανανεώνεται η λίστα αγώνων (χρεώνεται 1 αίτημα)

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
BANKROLL = 300                # € αρχική κάσα
KELLY_FRACTION = 0.25         # 25% του Kelly (λιγότερες διακυμάνσεις)
MAX_STAKE_PCT = 5             # ποτέ πάνω από 5% της κάσας σε ένα ματς
MIN_STAKE = 1                 # € ελάχιστο ποντάρισμα
REPORT_TIME = "23:30"         # ώρα Ελλάδας για τον ημερήσιο απολογισμό
SETTLE_AFTER_HOURS = 2.5      # ψάχνει αποτέλεσμα Χ ώρες μετά την έναρξη
SETTLE_MAX_TRIES = 3          # μετά από τόσες αποτυχίες → "χωρίς αποτέλεσμα"
SETTLE_MAX_PER_DAY = 5        # κάθε αποτέλεσμα = 1 αίτημα από τα 250/μήνα
QUOTA_RESERVE = 25            # αφήνει πάντα τόσα αιτήματα για τη λίστα αγώνων
KEEP_BETS_DAYS = 120          # για πόσες μέρες κρατάει το ιστορικό
CLV_MAX_PER_RUN = 5           # πόσους αγώνες ελέγχει για CLV ανά γύρο (δωρεάν αιτήματα)

# Μηδενισμός στατιστικών: άλλαξε αυτή την τιμή (π.χ. σε σημερινή ημερομηνία) για να ξεκινήσει
# από την αρχή το PnL. Το bot σβήνει τα παλιά στοιχήματα στον επόμενο γύρο.
STATS_RESET = "restart-1"
