# LinkedIn Job Agent 🤖

An automated LinkedIn job scraper and scorer that runs locally, connects to your Chrome session, and saves strong matches to Google Sheets.

## What it does
- Attaches to an existing Chrome session via Playwright CDP
- Scrapes LinkedIn Jobs search results (job cards + full JD)
- Pre-filters obvious mismatches without calling Gemini
- Scores remaining jobs using Gemini 2.5 Flash API
- Saves Strong Fit (score ≥8) and Maybe (score ≥6) to Google Sheets
- Tracks seen jobs in SQLite so re-runs skip already-processed jobs

## Setup

### 1. Launch Chrome with remote debugging
```powershell
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9223", "--profile-directory=Default", "--no-first-run", "--no-default-browser-check", "--user-data-dir=C:\chrome-debug-profile"
```

### 2. Install dependencies
```
pip install -r requirements.txt
```

### 3. Set environment variables
```powershell
$env:GEMINI_API_KEY = "your-gemini-api-key"
```

### 4. Add your credentials (not committed to git)
- `credentials.json` — Google service account for Sheets access
- `knowledge_base.json` — Your profile and scoring preferences

### 5. Run
```
python main.py
```

## Project Structure
```
linkedin-job-agent/
├── main.py
├── config.py
├── requirements.txt
├── modules/
│   ├── browser.py      # CDP connection to Chrome
│   ├── scraper.py      # LinkedIn job card + JD scraper
│   ├── prefilter.py    # Fast pre-filter before Gemini
│   ├── scorer.py       # Gemini 2.5 Flash scoring
│   ├── sheets.py       # Google Sheets writer
│   └── database.py     # SQLite seen-jobs tracker
```

## Notes
- `credentials.json` and `knowledge_base.json` are gitignored — never commit these
- Chrome must be running on port 9223 before you run `main.py`
- Google Sheet ID is configured in `config.py`
