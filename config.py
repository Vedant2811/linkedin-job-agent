import json
import os

from dotenv import load_dotenv

load_dotenv()

# ─── Google Sheets ────────────────────────────────────────────────
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID", "")
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

# ─── Recruiter discovery ──────────────────────────────────────────
RECRUITER_TAB              = "Recruiter Contacts"
RECRUITER_SEARCH_ENABLED   = True
SMTP_TIMEOUT               = 5
EMAIL_CONFIDENCE_THRESHOLD = "medium"

# ─── Recruiter outreach ───────────────────────────────────────────
RECRUITER_OUTREACH_MODE    = "draft"  # "draft" | "disabled"
CONNECTION_NOTE_TEMPLATE   = (
    "Hi {first_name}, I came across the {job_title} role at {company} "
    "and wanted to connect. Would love to learn more about the opportunity!"
)

# ─── Knowledge base ───────────────────────────────────────────────
with open("knowledge_base.json", "r") as f:
    KNOWLEDGE_BASE = json.load(f)
