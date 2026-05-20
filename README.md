# LinkedIn Job Agent

An automated LinkedIn job scraper and scorer that runs locally, connects to your existing Chrome session, and saves strong matches to Google Sheets — with optional recruiter discovery.

## What it does

- Attaches to a running Chrome session via Playwright CDP (no login automation)
- Scrapes LinkedIn Jobs search results: job cards + full job descriptions
- Pre-filters obvious mismatches without burning Gemini API quota
- Scores remaining jobs with **Gemini 2.5 Flash** against your knowledge base
- Saves **Strong Fit** (score ≥ 8) and **Maybe** (score ≥ 6) jobs to Google Sheets
- For every Strong Fit, optionally searches LinkedIn for a recruiter contact and guesses their email
- Tracks all seen jobs in SQLite — re-runs automatically skip already-processed listings

## Prerequisites

- Python 3.11+
- Google Chrome installed
- LinkedIn account (logged in to Chrome)
- [Gemini API key](https://aistudio.google.com/app/apikey) (free tier works)
- Google Cloud service account with Sheets API enabled (`credentials.json`)

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd linkedin-job-agent
pip install -r requirements.txt
playwright install chromium
```

### 2. Create your `.env` file

```
GEMINI_API_KEY=your-gemini-api-key-here
SPREADSHEET_ID=your-google-spreadsheet-id-here
```

Both values are required. The Spreadsheet ID is the long string in your Google Sheet URL:
`https://docs.google.com/spreadsheets/d/THIS_PART_HERE/edit`

### 3. Add your private files (not committed to git)

| File | Purpose |
|---|---|
| `credentials.json` | Google service account key — download from Google Cloud Console |
| `knowledge_base.json` | Your profile, skills, and scoring preferences |

`credentials.json` must belong to a service account that has **Editor** access to your Google Sheet.

### 4. Launch Chrome with remote debugging

**Windows (PowerShell):**
```powershell
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  -ArgumentList "--remote-debugging-port=9223", `
                "--profile-directory=Default", `
                "--user-data-dir=C:\chrome-debug-profile"
```

**macOS:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9223 --profile-directory=Default
```

Log in to LinkedIn and navigate to your Jobs search with filters already set.

### 5. Run

```bash
python main.py
```

## Google Sheets setup

The agent creates and manages three tabs automatically:

| Tab | Contents |
|---|---|
| **Strong Fit** | Jobs scored ≥ 8 — title, company, score, reasoning, connection note, recruiter info |
| **Maybe** | Jobs scored 6–7 — same columns |
| **Recruiter Contacts** | Recruiter names, LinkedIn URLs, guessed emails, and confidence level |

The header row is written and frozen on first run. Subsequent runs append rows; the header is never overwritten.

## Configuration (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `STRONG_FIT_THRESHOLD` | `8` | Minimum score for Strong Fit tab |
| `MAYBE_THRESHOLD` | `6` | Minimum score for Maybe tab |
| `MAX_JOBS` | `100` | Max jobs to process per run |
| `CHROME_DEBUG_PORT` | `9223` | CDP port Chrome is listening on |
| `JOB_PAGE_DELAY` | `2` | Seconds between individual job fetches |
| `LISTING_PAGE_DELAY` | `3` | Seconds between listing pages |
| `RECRUITER_SEARCH_ENABLED` | `True` | Enable/disable recruiter discovery |
| `EMAIL_CONFIDENCE_THRESHOLD` | `"medium"` | Min confidence to write recruiter row (`"high"` / `"medium"`) |

## Project structure

```
linkedin-job-agent/
├── main.py                    # Entry point and main loop
├── config.py                  # All tuneable settings
├── requirements.txt
├── modules/
│   ├── browser.py             # CDP connection to Chrome
│   ├── scraper.py             # Job card + full JD scraper
│   ├── prefilter.py           # Fast pre-filter before Gemini
│   ├── scorer.py              # Gemini 2.5 Flash scoring
│   ├── sheets.py              # Google Sheets writer
│   ├── database.py            # SQLite seen-jobs tracker
│   └── recruiter_finder.py    # LinkedIn recruiter search + email guessing
├── .env                       # Your secrets (gitignored)
├── credentials.json           # Service account key (gitignored)
└── knowledge_base.json        # Your profile and preferences (gitignored)
```

## Notes

- Chrome must be running on the configured debug port before you run `main.py`
- The agent never clicks Apply or sends any messages — it is read-only on LinkedIn
- Recruiter email confidence levels: `high` (Gravatar + web search hit), `medium` (one signal), `low` (neither — not written to sheet)
- To reset the database and clear all sheet rows: run `python reset.py` (prompts for confirmation)
