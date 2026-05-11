import re


class PreFilter:
    def __init__(self, kb: dict):
        self.kb = kb
        self.rejected_titles = [
            t.lower() for t in kb["job_preferences"]["rejected_titles"]
        ]
        self.blacklist = [
            c.lower()
            for c in kb["job_preferences"].get("blacklist_companies", [])
            if not c.startswith("TODO")
        ]

        # Hard year-experience patterns to reject from JD
        self._exp_patterns = [
            (r"\b(7|8|9|10|\d{2})\s*\+?\s*years?\s*(of\s+)?(experience|exp)\b", "Too much experience required"),
            (r"minimum\s+(7|8|9|10)\s*years?", "Minimum experience too high"),
        ]

        # Primary tech-stack rejection keywords (title context)
        self._wrong_stack = [
            "php", "ruby on rails", ".net developer",
            "golang developer", "rust developer",
        ]

    # ─────────────────────────────────────────────────────────────
    # Stage 1 — card-level check (no JD needed)
    # ─────────────────────────────────────────────────────────────

    def check(self, card: dict) -> tuple[bool, str]:
        title   = card.get("title", "").lower()
        company = card.get("company", "").lower()

        # Rejected job titles
        for rejected in self.rejected_titles:
            if self._title_matches(title, rejected):
                return False, f"Rejected title match: '{rejected}'"

        # Blacklisted companies
        for bl in self.blacklist:
            if bl and bl in company:
                return False, "Blacklisted company"

        # Avoided industries (body-shopping signals in company name)
        avoid_signals = [
            "staffing", "consulting", "outsourcing", "manpower",
            "recruitment", "talent solutions",
        ]
        for signal in avoid_signals:
            if signal in company:
                return False, f"Possible staffing/outsourcing firm: '{signal}' in company name"

        return True, ""

    # ─────────────────────────────────────────────────────────────
    # Stage 2 — JD-level check (after fetching full description)
    # ─────────────────────────────────────────────────────────────

    def check_jd(self, jd_text: str) -> tuple[bool, str]:
        jd_lower = jd_text.lower()

        # Experience year requirements
        for pattern, reason in self._exp_patterns:
            if re.search(pattern, jd_lower):
                return False, reason

        # Wrong primary stack explicitly stated
        for stack in self._wrong_stack:
            if stack in jd_lower:
                return False, f"Wrong primary stack: '{stack}'"

        # Hard red flags from knowledge base
        hard_flags = [
            (r"equity.{0,20}only|unpaid|no\s+base\s+salary", "Equity-only / unpaid role"),
            (r"wordpress|shopify\s+developer|elementor", "CMS dev role"),
            (r"\bqa\b.{0,20}engineer|quality\s+assurance\s+engineer|sdet\b", "QA/SDET role"),
            (r"android\s+developer|ios\s+developer|react\s+native\s+developer|flutter\s+developer", "Mobile dev role"),
        ]
        for pattern, reason in hard_flags:
            if re.search(pattern, jd_lower):
                return False, reason

        return True, ""

    # ─────────────────────────────────────────────────────────────
    # Helper
    # ─────────────────────────────────────────────────────────────

    def _title_matches(self, title: str, rejected: str) -> bool:
        if rejected in title:
            return True
        # Word-level overlap check
        r_words = set(rejected.split())
        t_words = set(title.split())
        if len(r_words) >= 2 and len(r_words & t_words) >= 2:
            return True
        return False
