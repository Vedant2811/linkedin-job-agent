import sys
from playwright.sync_api import sync_playwright, Page


class BrowserManager:
    def __init__(self, port: int = 9222):
        self.port = port
        self._playwright = None
        self.browser = None
        self.page: Page | None = None
        self._detail_tab: Page | None = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        try:
            self.browser = self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{self.port}"
            )
        except Exception:
            print(f"\n❌ Could not connect to Chrome on port {self.port}.")
            print("   Make sure Chrome was launched with:")
            print('   chrome --remote-debugging-port=9222')
            print("   See README.md for full setup instructions.")
            sys.exit(1)

        self.page = self._find_linkedin_tab()
        if not self.page:
            print("\n❌ No LinkedIn Jobs tab found in Chrome.")
            print("   Open linkedin.com/jobs in Chrome and set your filters, then re-run.")
            sys.exit(1)

        print(f"✅ Connected to Chrome → {self.page.url[:80]}")
        return self

    def __exit__(self, *args):
        if self._detail_tab:
            try:
                self._detail_tab.close()
            except Exception:
                pass
        if self._playwright:
            self._playwright.stop()

    def _find_linkedin_tab(self) -> Page | None:
        for context in self.browser.contexts:
            for page in context.pages:
                if "linkedin.com/jobs" in page.url:
                    return page
        return None

    def new_tab(self) -> Page:
        context = self.browser.contexts[0]
        if self._detail_tab is None or self._detail_tab.is_closed():
            self._detail_tab = context.new_page()
        return self._detail_tab

    def recover_main_page(self) -> bool:
        found = self._find_linkedin_tab()
        if found:
            self.page = found
            return True
        return False
