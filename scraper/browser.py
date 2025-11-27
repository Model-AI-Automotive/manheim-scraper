import asyncio
import json
import random
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class AuctionBrowser:
    """
    Playwright wrapper for auction site automation.
    Handles login, search, pagination, and navigation with rate limiting.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.selectors = config["selectors"]
        self.timeouts = config.get("timeouts", {})
        self.rate_limit = config.get("rate_limit", {"min_delay_ms": 2000, "max_delay_ms": 5000})

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self, headless: bool = True):
        """Launch browser with anti-detection measures"""
        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )

        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
        )

        # Add stealth scripts
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        self.page = await self.context.new_page()

        # Set default timeout
        self.page.set_default_timeout(self.timeouts.get("element", 10000))

    async def close(self):
        """Clean up browser resources"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _delay(self):
        """Random delay between actions to avoid detection"""
        delay_ms = random.randint(
            self.rate_limit["min_delay_ms"],
            self.rate_limit["max_delay_ms"]
        )
        await asyncio.sleep(delay_ms / 1000)

    async def _safe_click(self, selector: str, timeout: int = None) -> bool:
        """Safely click an element with retries"""
        timeout = timeout or self.timeouts.get("element", 10000)
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            await self.page.click(selector)
            return True
        except Exception as e:
            print(f"Click failed for {selector}: {e}")
            return False

    async def _safe_fill(self, selector: str, value: str, timeout: int = None) -> bool:
        """Safely fill an input with retries"""
        timeout = timeout or self.timeouts.get("element", 10000)
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            await self.page.fill(selector, value)
            return True
        except Exception as e:
            print(f"Fill failed for {selector}: {e}")
            return False

    async def login(self, username: str, password: str) -> bool:
        """
        Login to auction site.
        Returns True on success, False on failure.
        """
        sel = self.selectors["login"]

        print(f"Navigating to login page...")
        await self.page.goto(
            self.config["urls"]["login"],
            wait_until="networkidle",
            timeout=self.timeouts.get("navigation", 30000)
        )
        await self._delay()

        # Fill credentials
        print("Entering credentials...")
        await self._safe_fill(sel["username"], username)
        await self._delay()
        await self._safe_fill(sel["password"], password)
        await self._delay()

        # Submit
        print("Submitting login...")
        await self._safe_click(sel["submit"])

        # Wait for result
        try:
            # Wait for either success indicator or error message
            await self.page.wait_for_selector(
                f"{sel['success_indicator']}, {sel['error_message']}",
                timeout=self.timeouts.get("navigation", 30000)
            )

            # Check which one appeared
            success = await self.page.query_selector(sel["success_indicator"])
            if success:
                print("Login successful!")
                return True
            else:
                error_el = await self.page.query_selector(sel["error_message"])
                if error_el:
                    error_text = await error_el.text_content()
                    print(f"Login failed: {error_text}")
                return False

        except Exception as e:
            print(f"Login timeout or error: {e}")
            return False

    async def search(self, criteria: "SearchCriteria") -> bool:
        """
        Fill search form and submit.
        Returns True on success.
        """
        sel = self.selectors["search"]

        print(f"Navigating to search page...")
        await self.page.goto(
            self.config["urls"]["search"],
            wait_until="networkidle",
            timeout=self.timeouts.get("navigation", 30000)
        )
        await self._delay()

        # Fill make
        if criteria.make:
            print(f"Setting make: {criteria.make}")
            await self._safe_fill(sel["make_input"], criteria.make)
            await self._delay()

            # Wait for dropdown and select
            try:
                await self.page.wait_for_selector(sel["make_dropdown"], timeout=5000)
                await self.page.keyboard.press("ArrowDown")
                await self.page.keyboard.press("Enter")
                await self._delay()
            except:
                print("Make dropdown not found, continuing...")

        # Fill model
        if criteria.model:
            print(f"Setting model: {criteria.model}")
            await self._safe_fill(sel["model_input"], criteria.model)
            await self._delay()

            try:
                await self.page.wait_for_selector(sel["model_dropdown"], timeout=5000)
                await self.page.keyboard.press("ArrowDown")
                await self.page.keyboard.press("Enter")
                await self._delay()
            except:
                print("Model dropdown not found, continuing...")

        # Set year range
        if criteria.year_min:
            print(f"Setting year min: {criteria.year_min}")
            try:
                await self.page.select_option(sel["year_from"], str(criteria.year_min))
                await self._delay()
            except:
                print("Year from selector not found, trying fill...")
                await self._safe_fill(sel["year_from"], str(criteria.year_min))

        if criteria.year_max:
            print(f"Setting year max: {criteria.year_max}")
            try:
                await self.page.select_option(sel["year_to"], str(criteria.year_max))
                await self._delay()
            except:
                print("Year to selector not found, trying fill...")
                await self._safe_fill(sel["year_to"], str(criteria.year_max))

        # Submit search
        print("Submitting search...")
        await self._safe_click(sel["search_button"])

        try:
            await self.page.wait_for_load_state("networkidle", timeout=self.timeouts.get("page_load", 60000))
            return True
        except Exception as e:
            print(f"Search submission error: {e}")
            return False

    async def get_page_html(self) -> str:
        """Get current page HTML content"""
        return await self.page.content()

    async def get_current_url(self) -> str:
        """Get current page URL"""
        return self.page.url

    async def has_next_page(self) -> bool:
        """Check if there's a next page of results"""
        sel = self.selectors["results"]["pagination_next"]
        try:
            element = await self.page.query_selector(sel)
            if element:
                # Check if it's not disabled
                is_disabled = await element.get_attribute("disabled")
                class_name = await element.get_attribute("class") or ""
                return not is_disabled and "disabled" not in class_name
            return False
        except:
            return False

    async def go_next_page(self) -> bool:
        """Navigate to next page of results"""
        sel = self.selectors["results"]["pagination_next"]

        if not await self.has_next_page():
            return False

        try:
            await self._safe_click(sel)
            await self._delay()
            await self.page.wait_for_load_state("networkidle", timeout=self.timeouts.get("page_load", 60000))
            return True
        except Exception as e:
            print(f"Failed to go to next page: {e}")
            return False

    async def go_to_listing(self, url: str) -> str:
        """Navigate to a listing detail page and return HTML"""
        await self.page.goto(
            url,
            wait_until="networkidle",
            timeout=self.timeouts.get("navigation", 30000)
        )
        await self._delay()
        return await self.page.content()

    async def save_cookies(self, path: str = "cookies.json"):
        """Save session cookies for reuse"""
        cookies = await self.context.cookies()
        Path(path).write_text(json.dumps(cookies, indent=2))
        print(f"Saved {len(cookies)} cookies to {path}")

    async def load_cookies(self, path: str = "cookies.json") -> bool:
        """Load saved cookies. Returns True if loaded successfully."""
        cookie_path = Path(path)
        if not cookie_path.exists():
            return False

        try:
            cookies = json.loads(cookie_path.read_text())
            await self.context.add_cookies(cookies)
            print(f"Loaded {len(cookies)} cookies from {path}")
            return True
        except Exception as e:
            print(f"Failed to load cookies: {e}")
            return False

    async def is_logged_in(self) -> bool:
        """Check if current session is authenticated"""
        sel = self.selectors["login"]["success_indicator"]
        try:
            element = await self.page.query_selector(sel)
            return element is not None
        except:
            return False

    async def screenshot(self, path: str = "screenshot.png"):
        """Take a screenshot for debugging"""
        await self.page.screenshot(path=path, full_page=True)
        print(f"Screenshot saved to {path}")
