import re
import time
from playwright.sync_api import Page


class JobScraper:
    def __init__(self, browser_manager):
        self.bm = browser_manager
        self.page: Page = browser_manager.page

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def get_job_cards_on_page(self) -> list[dict]:
        """Return all job cards visible on the current listing page."""
        jobs = []

        # LinkedIn now renders job cards as div[role="button"], not <li> or <a>
        try:
            self.page.wait_for_selector('div[role="button"]', timeout=10_000)
        except Exception:
            print("  ⚠️  Timed out waiting for job cards.")
            return jobs

        self._scroll_left_panel()

        # ── Collect card text & index via JS ──────────────────────
        # Cards are div[role="button"] in the left panel (x<400, height>60)
        raw_cards = self.page.evaluate("""() => {
            return [...document.querySelectorAll('div[role="button"]')]
                .map((el, idx) => ({ idx, r: el.getBoundingClientRect(), text: el.innerText }))
                .filter(c => c.r.x < 400 && c.r.y > 180 && c.r.height > 60 && c.text.trim().length > 10)
                .map(c => {
                    const lines = c.text.trim().split('\\n').map(l => l.trim()).filter(Boolean);
                    // Remove "Selected," prefix on the currently active card
                    if (lines[0] && lines[0].startsWith('Selected,')) lines.shift();
                    const title   = (lines[0] || '').replace('(Verified job)', '').trim();
                    // Title is repeated on line 1 as aria text – skip it
                    const rest    = lines.slice(1).filter(l => l !== title);
                    const company = rest[0] || '';
                    const location = rest[1] || '';
                    return { idx: c.idx, title, company, location };
                });
        }""")

        seen_ids: set[str] = set()

        for card in raw_cards:
            # Click the card → LinkedIn updates URL to ?currentJobId=XXXXXX
            try:
                self.page.evaluate("""(idx) => {
                    const cards = [...document.querySelectorAll('div[role="button"]')]
                        .filter(el => {
                            const r = el.getBoundingClientRect();
                            return r.x < 400 && r.y > 180 && r.height > 60 && el.innerText.trim().length > 10;
                        });
                    if (cards[idx]) cards[idx].click();
                }""", card["idx"])

                self.page.wait_for_timeout(900)   # let URL update

                url = self.page.url
                m = re.search(r'currentJobId=(\d+)', url)
                if not m:
                    continue
                job_id = m.group(1)

            except Exception as e:
                print(f"    ⚠️  Card click failed: {e}")
                continue

            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            jobs.append({
                "job_id":   job_id,
                "title":    card["title"],
                "company":  card["company"],
                "location": card["location"],
                "job_url":  f"https://www.linkedin.com/jobs/view/{job_id}/",
            })

        return jobs

    def get_job_description(self, job_url: str) -> dict:
        """Open the job URL in a new tab and scrape full details."""
        tab = self.bm.new_tab()
        result = {
            "title": "",
            "company": "",
            "location": "",
            "description": "",
            "apply_url": None,
            "is_easy_apply": False,
            "recruiter_name": None,
            "recruiter_linkedin": None,
            "recruiter_email": None,
        }

        try:
            tab.goto(job_url, wait_until="domcontentloaded", timeout=15_000)
            tab.wait_for_timeout(2_000)

            result["title"] = self._first_text(tab, [
                "h1.job-details-jobs-unified-top-card__job-title",
                ".jobs-unified-top-card__job-title h1",
                "h1.t-24",
            ])
            result["company"] = self._first_text(tab, [
                ".job-details-jobs-unified-top-card__company-name a",
                ".jobs-unified-top-card__company-name a",
                ".job-details-jobs-unified-top-card__company-name",
            ])
            result["location"] = self._first_text(tab, [
                ".job-details-jobs-unified-top-card__bullet",
                ".jobs-unified-top-card__bullet",
                ".job-details-jobs-unified-top-card__workplace-type",
            ])

            try:
                see_more = tab.query_selector(
                    "button.jobs-description__footer-button, "
                    "button[aria-label='Click to see more description']"
                )
                if see_more:
                    see_more.click()
                    tab.wait_for_timeout(500)
            except Exception:
                pass

            result["description"] = self._first_text(tab, [
                "#job-details",
                ".jobs-description__content",
                ".job-details-about-the-job-module__description",
            ])

            apply_btn = tab.query_selector(
                ".jobs-apply-button--top-card, "
                ".jobs-apply-button, "
                "button[data-job-id]"
            )
            if apply_btn:
                btn_text = apply_btn.inner_text().lower()
                if "easy apply" in btn_text:
                    result["is_easy_apply"] = True
                    result["apply_url"] = "LinkedIn Easy Apply"
                else:
                    href = apply_btn.get_attribute("href")
                    if href:
                        result["apply_url"] = href

            recruiter_el = tab.query_selector(
                ".hirer-card__hirer-information a, "
                ".job-details-hiring-company-module a, "
                "[data-live-test-hiring-details-recruiter] a"
            )
            if recruiter_el:
                result["recruiter_name"] = recruiter_el.inner_text().strip()
                result["recruiter_linkedin"] = recruiter_el.get_attribute("href")

            if result["description"]:
                m = re.search(
                    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
                    result["description"],
                )
                if m:
                    result["recruiter_email"] = m.group()

        except Exception as e:
            print(f"    ⚠️  Error fetching job page: {e}")
        finally:
            pass

        return result

    def next_page(self) -> bool:
        """Click the Next button or navigate via URL start parameter."""
        try:
            self.page.evaluate("() => document.readyState")
        except Exception:
            print("  ⚠️  Main page was closed — attempting to recover...")
            if self.bm.recover_main_page():
                self.page = self.bm.page
            else:
                print("  ❌  Could not recover page.")
                return False

        try:
            clicked = self.page.evaluate("""() => {
                const btn = [...document.querySelectorAll('button')]
                    .find(b => b.innerText.trim() === 'Next' && !b.disabled);
                if (btn) { btn.click(); return true; }
                return false;
            }""")
            if clicked:
                self.page.wait_for_timeout(3_000)
                return True

            m = re.search(r'[?&]start=(\d+)', self.page.url)
            current_start = int(m.group(1)) if m else 0
            next_start = current_start + 25
            next_url = re.sub(r'start=\d+', f'start={next_start}', self.page.url) \
                if 'start=' in self.page.url else self.page.url + f'&start={next_start}'

            self.page.goto(next_url, wait_until='domcontentloaded', timeout=15_000)
            self.page.wait_for_timeout(2_500)

            count = self.page.evaluate("""() =>
                [...document.querySelectorAll('div[role="button"]')]
                    .filter(el => { const r = el.getBoundingClientRect();
                        return r.x < 400 && r.y > 180 && r.height > 60; }).length
            """)
            return count > 0

        except Exception as e:
            print(f"  ⚠️  Pagination error: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _scroll_left_panel(self, rounds: int = 10, pause_ms: int = 1200) -> None:
        """Scroll the left panel to trigger lazy-loading of all cards."""
        # Mark the left-panel scrollable container
        self.page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                if (r.x < 50 && r.width > 200 && r.width < 500 && r.height > 400
                    && (s.overflowY === 'scroll' || s.overflowY === 'auto')) {
                    el.setAttribute('data-scraper-panel', 'true');
                    break;
                }
            }
        }""")

        prev = 0
        for _ in range(rounds):
            count = self.page.evaluate("""() =>
                [...document.querySelectorAll('div[role="button"]')]
                    .filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.x < 400 && r.y > 180 && r.height > 60;
                    }).length
            """)
            if count >= 25 or (count == prev and prev > 0):
                break
            prev = count

            scrolled = self.page.evaluate("""() => {
                const el = document.querySelector('[data-scraper-panel]');
                if (el) { el.scrollTop += 600; return true; }
                return false;
            }""")
            if not scrolled:
                self.page.keyboard.press("End")

            self.page.wait_for_timeout(pause_ms)

    def _first_text(self, page, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    return el.inner_text().strip()
            except Exception:
                continue
        return ""

    def _extract_job_id(self, url: str) -> str | None:
        m = re.search(r"/jobs/view/(\d+)", url)
        return m.group(1) if m else None

    def _extract_card_meta(self, link) -> tuple[str, str]:
        company = ""
        location = ""
        try:
            card = link.evaluate_handle(
                "el => el.closest('li') || el.closest('.job-card-container')"
            )
            if card:
                for sel in [".job-card-container__primary-description", ".artdeco-entity-lockup__subtitle"]:
                    el = card.query_selector(sel)
                    if el:
                        company = el.inner_text().strip()
                        break
                for sel in [".job-card-container__metadata-item", ".artdeco-entity-lockup__caption"]:
                    el = card.query_selector(sel)
                    if el:
                        location = el.inner_text().strip()
                        break
        except Exception:
            pass
        return company, location

    def _safe_text(self, el) -> str:
        try:
            return el.inner_text().strip()
        except Exception:
            return ""

    def _safe_attr(self, el, attr: str) -> str:
        try:
            val = el.get_attribute(attr)
            return val.strip() if val else ""
        except Exception:
            return ""