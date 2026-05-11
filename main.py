import json
import os
import sys
import time

import config
from modules.browser import BrowserManager
from modules.database import JobDatabase
from modules.prefilter import PreFilter
from modules.scorer import GeminiScorer
from modules.scraper import JobScraper
from modules.sheets import SheetsWriter


def main():
    print("\n" + "=" * 60)
    print("🤖  LinkedIn Job Agent")
    print("=" * 60)

    # ── Pre-flight checks ────────────────────────────────────────
    if not os.environ.get("GEMINI_API_KEY"):
        print("❌  GEMINI_API_KEY not set.")
        print("    Run:  export GEMINI_API_KEY=your_key_here")
        sys.exit(1)

    if not os.path.exists(config.CREDENTIALS_FILE):
        print(f"❌  {config.CREDENTIALS_FILE} not found in project root.")
        sys.exit(1)

    if not os.path.exists("knowledge_base.json"):
        print("❌  knowledge_base.json not found in project root.")
        sys.exit(1)

    # ── Init ─────────────────────────────────────────────────────
    with open("knowledge_base.json") as f:
        kb = json.load(f)

    print(f"📋  Loaded knowledge base for: {kb['profile']['name']}")

    db       = JobDatabase("seen_jobs.db")
    prefilter = PreFilter(kb)
    scorer   = GeminiScorer(kb)
    sheets   = SheetsWriter(config.CREDENTIALS_FILE, config.SPREADSHEET_ID)

    print(f"📊  Google Sheets connected")
    print(f"🗄️   Previously seen jobs in DB: {db.seen_count()}")
    print(f"🎯  Target: up to {config.MAX_JOBS} jobs this run")
    print(
        f"📈  Thresholds — Strong Fit: ≥{config.STRONG_FIT_THRESHOLD}  |  Maybe: ≥{config.MAYBE_THRESHOLD}"
    )

    stats = {
        "scanned": 0,
        "skipped_seen": 0,
        "pre_filtered": 0,
        "scored": 0,
        "strong_fit": 0,
        "maybe": 0,
        "errors": 0,
    }

    # ── Main loop ────────────────────────────────────────────────
    print("\n🔌  Connecting to Chrome...")

    with BrowserManager(port=config.CHROME_DEBUG_PORT) as bm:
        scraper  = JobScraper(bm)
        page_num = 1

        while stats["scanned"] < config.MAX_JOBS:
            print(f"\n{'─' * 60}")
            print(
                f"📄  Page {page_num}  |  Scanned: {stats['scanned']}/{config.MAX_JOBS}"
                f"  |  Saved: ✅{stats['strong_fit']} 🟡{stats['maybe']}"
            )
            print("─" * 60)

            cards = scraper.get_job_cards_on_page()

            if not cards:
                print("  ⚠️  No job cards found on this page. Stopping.")
                break

            print(f"  Found {len(cards)} job cards")

            for card in cards:
                if stats["scanned"] >= config.MAX_JOBS:
                    break

                job_id  = card["job_id"]
                stats["scanned"] += 1

                label = f"[{stats['scanned']:>3}/{config.MAX_JOBS}]"
                title   = (card.get("title") or "?")[:45]
                company = (card.get("company") or "?")[:28]

                # ── Already seen? ─────────────────────────────
                if db.is_seen(job_id):
                    stats["skipped_seen"] += 1
                    print(f"  {label} ⏭️   Already seen  →  {title} @ {company}")
                    continue

                db.mark_seen(job_id, card.get("title", ""), card.get("company", ""))
                print(f"\n  {label} 🔍  {title} @ {company}")

                # ── Stage 1: title/company pre-filter ─────────
                passed, reason = prefilter.check(card)
                if not passed:
                    stats["pre_filtered"] += 1
                    print(f"           ❌  Pre-filtered (card): {reason}")
                    continue

                # ── Fetch full JD ─────────────────────────────
                print("           📥  Fetching job details...")
                try:
                    jd = scraper.get_job_description(card["job_url"])
                except Exception as e:
                    stats["errors"] += 1
                    print(f"           ⚠️  Fetch error: {e}")
                    continue

                time.sleep(config.JOB_PAGE_DELAY)

                # ── Stage 2: JD-level pre-filter ──────────────
                if jd.get("description"):
                    passed_jd, reason_jd = prefilter.check_jd(jd["description"])
                    if not passed_jd:
                        stats["pre_filtered"] += 1
                        print(f"           ❌  Pre-filtered (JD): {reason_jd}")
                        continue

                # ── Gemini scoring ────────────────────────────
                print("           🤖  Scoring with Gemini...")
                try:
                    result = scorer.score(card, jd)
                except Exception as e:
                    stats["errors"] += 1
                    print(f"           ⚠️  Scorer error: {e}")
                    continue

                stats["scored"] += 1
                score = result.get("score", 0)

                if score >= config.STRONG_FIT_THRESHOLD:
                    stats["strong_fit"] += 1
                    print(f"           ✅  Score {score}/10  →  Strong Fit!")
                    sheets.write_strong_fit(card, jd, result)

                elif score >= config.MAYBE_THRESHOLD:
                    stats["maybe"] += 1
                    print(f"           🟡  Score {score}/10  →  Maybe")
                    sheets.write_maybe(card, jd, result)

                else:
                    print(f"           ⬇️   Score {score}/10  →  Not a fit")

                time.sleep(1)

            # ── Next page ─────────────────────────────────────
            print(f"\n  ➡️   Going to page {page_num + 1}...")
            if not scraper.next_page():
                print("  🏁  No more pages.")
                break

            page_num += 1
            time.sleep(config.LISTING_PAGE_DELAY)

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("✅  Run complete! Summary:")
    print(f"    Total scanned     : {stats['scanned']}")
    print(f"    Already seen (DB) : {stats['skipped_seen']}")
    print(f"    Pre-filtered      : {stats['pre_filtered']}")
    print(f"    Scored by Gemini  : {stats['scored']}")
    print(f"    ✅  Strong Fit    : {stats['strong_fit']}")
    print(f"    🟡  Maybe         : {stats['maybe']}")
    print(f"    ⚠️   Errors        : {stats['errors']}")
    print("=" * 60)
    print(f"\n🔗  Open your sheet:")
    print(
        f"    https://docs.google.com/spreadsheets/d/{config.SPREADSHEET_ID}"
    )


if __name__ == "__main__":
    main()
