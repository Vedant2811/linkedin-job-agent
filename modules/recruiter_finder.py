import hashlib
import re
import time
import urllib.parse

import requests

import config

RECRUITER_RE = re.compile(
    r"recruiter|talent acquisition|hr\b|human resources|hiring manager|people ops|talent partner",
    re.IGNORECASE,
)

# LinkedIn geoUrn IDs for location-filtered people search
_GEO_URNS = {
    "hyderabad": "105556991",
    "bangalore":  "105214831",
    "bengaluru":  "105214831",
    "mumbai":     "102713980",
    "delhi":      "102713980",
    "pune":       "106164952",
    "chennai":    "106655533",
    "india":      "102713980",
}

# Noise patterns applied in Python after JS extraction
_HEADLINE_NOISE = re.compile(r"^•|mutual connection|2nd|3rd", re.IGNORECASE)
_SKIP_LINES     = re.compile(
    r"^(connect|follow|message|dismiss|see all|\d+ mutual|linkedin member)$",
    re.IGNORECASE,
)


class RecruiterFinder:
    def __init__(self, browser_manager):
        self.bm = browser_manager

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def find(self, company_name: str, job_url: str, jd: dict) -> dict:
        """Search for a recruiter contact at company_name. Never raises."""
        result = {
            "recruiter_name":     None,
            "recruiter_title":    None,
            "recruiter_linkedin": None,
            "email":              None,
            "confidence":         "not_found",
            "domain":             None,
        }

        try:
            location    = (jd.get("location") or "") if isinstance(jd, dict) else ""
            description = (jd.get("description") or "") if isinstance(jd, dict) else (jd or "")

            # Step 1: LinkedIn people search (location-filtered, two-pass)
            person = self._search_linkedin(company_name, location)
            if not person:
                print("    🔍  Recruiter: no LinkedIn match found")
                return result

            result["recruiter_name"]     = person["name"]
            result["recruiter_title"]    = person["headline"]
            result["recruiter_linkedin"] = person["url"]
            print(f"    🔍  Recruiter candidate: {person['name']} — {person['headline']}")

            # Step 2: company domain
            domain = self._extract_domain(description, company_name)
            result["domain"] = domain
            if not domain:
                result["confidence"] = "low"
                print("    ⚠️  Could not determine company domain")
                return result

            # Step 3: generate email candidates
            candidates = self._email_candidates(person["name"], domain)
            if not candidates:
                result["confidence"] = "low"
                return result

            # Step 4: verify the primary candidate via Gravatar + web search
            best = candidates[0]
            result["email"]      = best
            result["confidence"] = self._verify_email(best)
            print(f"    ✉️  Email: {best}  (confidence: {result['confidence']})")

        except Exception as e:
            print(f"    ⚠️  RecruiterFinder error: {e}")

        return result

    # ─────────────────────────────────────────────────────────────
    # Step 1: LinkedIn people search — location-filtered, two-pass
    # ─────────────────────────────────────────────────────────────

    def _search_linkedin(self, company_name: str, location: str) -> dict | None:
        """
        Pass 1 — city-level geoUrn filter (skipped if city not in lookup).
        Pass 2 — country-level geoUrn filter (skipped if country not in lookup).
        Returns None without falling back to an unfiltered global search.
        """
        city, country = self._extract_location_parts(location)

        passes = []
        if city.lower() in _GEO_URNS:
            passes.append(("Pass 1 (city)", _GEO_URNS[city.lower()]))
        if country.lower() in _GEO_URNS:
            passes.append(("Pass 2 (country)", _GEO_URNS[country.lower()]))

        if not passes:
            print(f"    ⚠️  Location '{location}' not in geo lookup — skipping recruiter search")
            return None

        kw = urllib.parse.quote(f"recruiter {company_name}")
        for label, urn_id in passes:
            try:
                geo = urllib.parse.quote(f"urn:li:geo:{urn_id}")
                url = (
                    f"https://www.linkedin.com/search/results/people/"
                    f"?keywords={kw}&geoUrn={geo}&origin=GLOBAL_SEARCH_HEADER"
                )
                person = self._run_people_search(url)
                if person:
                    print(f"    🌍  Recruiter found via {label}")
                    return person
            except Exception as e:
                print(f"    ⚠️  LinkedIn {label} error: {e}")

        print("    ⚠️  No recruiter matched across all geo passes")
        return None

    def _run_people_search(self, url: str) -> dict | None:
        """Navigate to a LinkedIn people-search URL and return the best recruiter match."""
        try:
            tab = self.bm.new_tab()
            tab.goto(url, wait_until="domcontentloaded", timeout=15_000)
            tab.wait_for_timeout(2_500)

            people = tab.evaluate("""() => {
                const results = [];
                const seen    = new Set();
                const NOISE   = /^•|mutual connection|2nd|3rd/i;

                function extractHeadline(card, nameText) {
                    const headlineEl = card.querySelector(
                        '.entity-result__primary-subtitle, ' +
                        '[class*="entity-result__primary-subtitle"], ' +
                        '[class*="primary-subtitle"]'
                    );
                    if (headlineEl) {
                        const t = headlineEl.innerText.trim();
                        if (t && !NOISE.test(t)) return t;
                    }
                    const lines = card.innerText
                        .split('\\n')
                        .map(l => l.trim())
                        .filter(l => l.length > 2 && l !== nameText && !NOISE.test(l));
                    return lines.length > 0 ? lines[0] : '';
                }

                // Primary selector — current LinkedIn search result template
                let cards = [...document.querySelectorAll(
                    'div[data-view-name="search-entity-result-universal-template"]'
                )];

                // Secondary fallback: entity-result divs directly under a ul/ol
                if (cards.length === 0) {
                    cards = [...document.querySelectorAll(
                        'ul > div[class*="entity-result"], ol > div[class*="entity-result"]'
                    )];
                }

                for (const card of cards.slice(0, 5)) {
                    const link = card.querySelector('a[href*="/in/"]');
                    if (!link) continue;
                    const url = link.href.split('?')[0];
                    if (seen.has(url)) continue;
                    seen.add(url);

                    const nameSpan = link.querySelector('span[aria-hidden="true"]');
                    const name = (nameSpan ? nameSpan.innerText : link.innerText).trim();
                    if (!name || name.length < 2) continue;

                    results.push({ name, headline: extractHeadline(card, name), url });
                }

                // Final fallback: walk all /in/ links when card selectors find nothing
                if (results.length === 0) {
                    const links = [...document.querySelectorAll('a[href*="/in/"]')]
                        .filter(a => {
                            const t = a.innerText.trim();
                            return t.length > 1 && t.length < 60;
                        });
                    for (const link of links.slice(0, 5)) {
                        const url = link.href.split('?')[0];
                        if (seen.has(url)) continue;
                        seen.add(url);

                        let headline = '';
                        let el = link.parentElement;
                        for (let i = 0; i < 6; i++) {
                            if (!el) break;
                            const lines = el.innerText
                                .split('\\n')
                                .map(l => l.trim())
                                .filter(l =>
                                    l.length > 2 &&
                                    l !== link.innerText.trim() &&
                                    !NOISE.test(l)
                                );
                            if (lines.length > 0) { headline = lines[0]; break; }
                            el = el.parentElement;
                        }

                        results.push({ name: link.innerText.trim(), headline, url });
                    }
                }

                return results;
            }""")

            time.sleep(2)

            if not people:
                return None

            for p in people:
                p["name"] = p["name"].title()
                if _SKIP_LINES.match(p.get("headline", "")):
                    p["headline"] = ""

            for p in people:
                if RECRUITER_RE.search(p.get("headline", "")):
                    return p

            return None  # no headline matched recruiter keywords on this pass

        except Exception as e:
            print(f"    ⚠️  People search error: {e}")
            return None

    # ─────────────────────────────────────────────────────────────
    # Location helpers
    # ─────────────────────────────────────────────────────────────

    def _extract_location_parts(self, location_str: str) -> tuple[str, str]:
        """Parse 'City, State, Country' → (city, country). Never raises."""
        if not location_str:
            return "", ""
        parts = [p.strip() for p in location_str.split(",")]
        city    = parts[0] if parts else ""
        country = parts[-1] if len(parts) > 1 else ""
        return city, country

    # ─────────────────────────────────────────────────────────────
    # Step 2: domain extraction
    # ─────────────────────────────────────────────────────────────

    def _extract_domain(self, jd_text: str, company_name: str) -> str | None:
        _SKIP = {"linkedin.com", "indeed.com", "glassdoor.com", "google.com",
                 "apple.com", "twitter.com", "facebook.com", "instagram.com"}

        if jd_text:
            for m in re.finditer(
                r"(?:https?://)?(?:www\.)?([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
                r"\.[a-zA-Z]{2,})",
                jd_text,
            ):
                domain = m.group(1).lower()
                if domain not in _SKIP and not any(s in domain for s in _SKIP):
                    return domain

        slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        return f"{slug}.com" if slug else None

    # ─────────────────────────────────────────────────────────────
    # Step 3: email candidate generation
    # ─────────────────────────────────────────────────────────────

    def _email_candidates(self, full_name: str, domain: str) -> list[str]:
        if not full_name or not domain:
            return []

        parts = [re.sub(r"[^a-z]", "", p) for p in full_name.lower().split()]
        parts = [p for p in parts if p]
        if not parts:
            return []

        first = parts[0]
        last  = parts[-1] if len(parts) >= 2 else ""

        if last:
            return [
                f"{first}.{last}@{domain}",
                f"{first[0]}.{last}@{domain}",
                f"{first}{last}@{domain}",
                f"{first[0]}{last}@{domain}",
                f"{first}@{domain}",
            ]
        return [f"{first}@{domain}"]

    # ─────────────────────────────────────────────────────────────
    # Step 4: email verification — Gravatar lookup + web search probe
    # ─────────────────────────────────────────────────────────────

    def _is_catchall_domain(self, domain: str) -> bool:
        """
        Probe Gravatar with a deliberately fake address.
        If Gravatar returns 200, the domain accepts any address (catch-all)
        and Gravatar hits for real addresses on this domain are meaningless.
        Returns False on any error so the caller stays conservative.
        """
        try:
            fake  = f"fake.doesnotexist123@{domain}".strip().lower()
            digest = hashlib.md5(fake.encode()).hexdigest()
            resp  = requests.get(
                f"https://www.gravatar.com/avatar/{digest}?d=404",
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _verify_email(self, email: str) -> str:
        """
        Verify email via Gravatar + web search.
        Gravatar is only trusted when the domain is not catch-all.
        Returns "high", "medium", or "low". Never raises.
        """
        domain       = email.split("@")[-1] if "@" in email else ""
        gravatar_hit = False
        search_hit   = False

        # ── Catch-all check (determines whether Gravatar is meaningful) ──
        catch_all = self._is_catchall_domain(domain)
        if catch_all:
            print("    ⚠️  Domain is catch-all — ignoring Gravatar result")
        else:
            print("    🎯  Domain is not catch-all — Gravatar result is trustworthy")

        # ── Method 1: Gravatar MD5 lookup (pure HTTP, no browser needed) ──
        if not catch_all:
            try:
                digest = hashlib.md5(email.strip().lower().encode()).hexdigest()
                resp = requests.get(
                    f"https://www.gravatar.com/avatar/{digest}?d=404",
                    timeout=5,
                )
                if resp.status_code == 200:
                    gravatar_hit = True
                    print("    ✅  Gravatar hit → email likely valid")
            except Exception:
                pass

        # ── Method 2: Web search probe (uses existing browser tab) ──
        try:
            tab     = self.bm.new_tab()
            encoded = urllib.parse.quote(f'"{email}"')
            tab.goto(
                f"https://www.google.com/search?q={encoded}",
                wait_until="domcontentloaded",
                timeout=15_000,
            )
            tab.wait_for_timeout(2_000)
            page_text = tab.inner_text("body")
            if email.lower() in page_text.lower():
                search_hit = True
                print("    🌐  Found in web search")
            # Return browser to LinkedIn — don't leave it on Google
            tab.goto(
                "https://www.linkedin.com",
                wait_until="domcontentloaded",
                timeout=10_000,
            )
        except Exception:
            pass

        # ── Confidence decision ──
        if catch_all:
            # Gravatar is unreliable — only web search counts
            if search_hit:
                return "medium"
            print("    ⚠️  No verification signal found")
            return "low"

        # Domain is not catch-all — Gravatar is trustworthy
        if gravatar_hit:
            return "high"   # Gravatar alone is sufficient when domain is clean
        if search_hit:
            return "medium"
        print("    ⚠️  No verification signal found")
        return "low"
