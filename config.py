import json

# ─── Google Sheets ────────────────────────────────────────────────
SPREADSHEET_ID   = "1XIlUjZJB9CsBfXHlk03fqGEaFo3NDuOeHBEcI77rf90"
CREDENTIALS_FILE = "credentials.json"

# ─── Sheet tab names ──────────────────────────────────────────────
STRONG_FIT_TAB = "Strong Fit"
MAYBE_TAB      = "Maybe"

# ─── Scoring thresholds ───────────────────────────────────────────
STRONG_FIT_THRESHOLD = 8
MAYBE_THRESHOLD      = 6

# ─── Agent limits ─────────────────────────────────────────────────
MAX_JOBS = 100

# ─── Chrome ───────────────────────────────────────────────────────
CHROME_DEBUG_PORT = 9223

# ─── Delays (seconds) ─────────────────────────────────────────────
JOB_PAGE_DELAY     = 2   # between individual job fetches
LISTING_PAGE_DELAY = 3   # between listing pages

# ─── Knowledge base ───────────────────────────────────────────────
with open("knowledge_base.json", "r") as f:
    KNOWLEDGE_BASE = json.load(f)
