# Migration Guide: Single Site to Multi-Site Architecture

This guide explains how to refactor the auction scraper from a single-site implementation to a multi-site architecture using the adapter pattern. **Do this when you're ready to add your second auction site.**

---

## Overview

### Current Architecture (Single Site)
```
/auction-scraper
  /config
    copart.yaml
    settings.py
  /scraper
    browser.py      # Copart-specific logic mixed in
    extractor.py
    storage.py
  /models
    schemas.py
  main.py
```

### Target Architecture (Multi-Site)
```
/auction-scraper
  /core
    browser.py      # Generic browser wrapper
    extractor.py    # AI extraction (shared)
    storage.py      # Database (shared)
    models.py       # Data models (shared)
    workflow.py     # Orchestration (shared)
    base_adapter.py # Abstract base class
  /sites
    __init__.py
    /copart
      __init__.py
      config.yaml
      adapter.py    # Copart-specific logic
    /iaai
      __init__.py
      config.yaml
      adapter.py    # IAAI-specific logic
  /cli
    __init__.py
    main.py         # Unified CLI
  requirements.txt
```

---

## Step 1: Create Core Module

### 1.1 Create directory structure

```bash
mkdir -p core sites/copart sites/iaai cli
touch core/__init__.py sites/__init__.py cli/__init__.py
touch sites/copart/__init__.py sites/iaai/__init__.py
```

### 1.2 Move and rename files

```bash
# Move models
mv models/schemas.py core/models.py

# Move storage (no changes needed)
mv scraper/storage.py core/storage.py

# Move extractor (minor changes needed)
mv scraper/extractor.py core/extractor.py

# Move config
mv config/copart.yaml sites/copart/config.yaml
mv config/settings.py core/settings.py
```

### 1.3 Create core/__init__.py

```python
from .models import SearchCriteria, CarListing, CarDetail, ScrapeRun
from .storage import Storage
from .extractor import ListingExtractor
from .browser import BaseBrowser
from .base_adapter import SiteAdapter
from .workflow import ScrapeWorkflow

__all__ = [
    "SearchCriteria",
    "CarListing", 
    "CarDetail",
    "ScrapeRun",
    "Storage",
    "ListingExtractor",
    "BaseBrowser",
    "SiteAdapter",
    "ScrapeWorkflow",
]
```

---

## Step 2: Create Base Browser Class

### core/browser.py

Extract the generic browser functionality, removing site-specific logic:

```python
import asyncio
import json
import random
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class BaseBrowser:
    """
    Generic Playwright browser wrapper.
    Site-specific logic belongs in adapters, not here.
    """
    
    def __init__(self, rate_limit: Dict[str, int] = None, timeouts: Dict[str, int] = None):
        self.rate_limit = rate_limit or {"min_delay_ms": 2000, "max_delay_ms": 5000}
        self.timeouts = timeouts or {"navigation": 30000, "element": 10000}
        
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
            ]
        )
        
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeouts.get("element", 10000))
        
    async def close(self):
        """Clean up browser resources"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
            
    async def delay(self):
        """Random delay between actions"""
        delay_ms = random.randint(
            self.rate_limit["min_delay_ms"],
            self.rate_limit["max_delay_ms"]
        )
        await asyncio.sleep(delay_ms / 1000)
        
    # === Core browser actions ===
    
    async def goto(self, url: str, wait_until: str = "networkidle") -> bool:
        """Navigate to URL"""
        try:
            await self.page.goto(
                url,
                wait_until=wait_until,
                timeout=self.timeouts.get("navigation", 30000)
            )
            return True
        except Exception as e:
            print(f"Navigation failed: {e}")
            return False
    
    async def click(self, selector: str, timeout: int = None) -> bool:
        """Click an element"""
        timeout = timeout or self.timeouts.get("element", 10000)
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            await self.page.click(selector)
            return True
        except Exception as e:
            print(f"Click failed for {selector}: {e}")
            return False
            
    async def fill(self, selector: str, value: str, timeout: int = None) -> bool:
        """Fill an input field"""
        timeout = timeout or self.timeouts.get("element", 10000)
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            await self.page.fill(selector, value)
            return True
        except Exception as e:
            print(f"Fill failed for {selector}: {e}")
            return False
            
    async def select(self, selector: str, value: str, timeout: int = None) -> bool:
        """Select dropdown option"""
        timeout = timeout or self.timeouts.get("element", 10000)
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            await self.page.select_option(selector, value)
            return True
        except Exception as e:
            print(f"Select failed for {selector}: {e}")
            return False
    
    async def keyboard_press(self, key: str):
        """Press a keyboard key"""
        await self.page.keyboard.press(key)
        
    async def wait_for_selector(self, selector: str, timeout: int = None) -> bool:
        """Wait for element to appear"""
        timeout = timeout or self.timeouts.get("element", 10000)
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except:
            return False
            
    async def wait_for_network_idle(self, timeout: int = None):
        """Wait for network to be idle"""
        timeout = timeout or self.timeouts.get("navigation", 30000)
        await self.page.wait_for_load_state("networkidle", timeout=timeout)
        
    async def query_selector(self, selector: str):
        """Get element by selector"""
        return await self.page.query_selector(selector)
        
    async def is_visible(self, selector: str) -> bool:
        """Check if element is visible"""
        try:
            element = await self.page.query_selector(selector)
            return element is not None and await element.is_visible()
        except:
            return False
    
    async def get_html(self) -> str:
        """Get page HTML"""
        return await self.page.content()
        
    async def get_url(self) -> str:
        """Get current URL"""
        return self.page.url
        
    async def screenshot(self, path: str = "screenshot.png"):
        """Take screenshot"""
        await self.page.screenshot(path=path, full_page=True)
        
    # === Cookie management ===
    
    async def save_cookies(self, path: str):
        """Save cookies to file"""
        cookies = await self.context.cookies()
        Path(path).write_text(json.dumps(cookies, indent=2))
        
    async def load_cookies(self, path: str) -> bool:
        """Load cookies from file"""
        cookie_path = Path(path)
        if not cookie_path.exists():
            return False
        try:
            cookies = json.loads(cookie_path.read_text())
            await self.context.add_cookies(cookies)
            return True
        except:
            return False
```

---

## Step 3: Create Base Adapter Class

### core/base_adapter.py

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from .models import SearchCriteria, CarListing, CarDetail
from .browser import BaseBrowser


class SiteAdapter(ABC):
    """
    Abstract base class for auction site adapters.
    
    Each site implements its own adapter with:
    - Login flow
    - Search form handling
    - Pagination logic
    - Any site-specific transformations
    
    The adapter uses composition (has-a browser) not inheritance.
    """
    
    # Override in subclass
    name: str = "base"
    
    def __init__(self, config_path: Path = None):
        """
        Initialize adapter with site config.
        
        Args:
            config_path: Path to config.yaml. If None, loads from 
                         sites/{name}/config.yaml
        """
        if config_path:
            self.config = self._load_config(config_path)
        else:
            default_path = (
                Path(__file__).parent.parent / "sites" / self.name / "config.yaml"
            )
            self.config = self._load_config(default_path)
            
        # Browser will be injected by workflow
        self.browser: Optional[BaseBrowser] = None
        
    def _load_config(self, path: Path) -> Dict[str, Any]:
        """Load YAML configuration"""
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(path) as f:
            return yaml.safe_load(f)
    
    def set_browser(self, browser: BaseBrowser):
        """Inject browser instance"""
        self.browser = browser
    
    @property
    def selectors(self) -> Dict[str, Any]:
        """Get selectors from config"""
        return self.config.get("selectors", {})
    
    @property
    def urls(self) -> Dict[str, str]:
        """Get URLs from config"""
        return self.config.get("urls", {})
    
    @property
    def rate_limit(self) -> Dict[str, int]:
        """Get rate limit settings"""
        return self.config.get("rate_limit", {"min_delay_ms": 2000, "max_delay_ms": 5000})
    
    @property
    def timeouts(self) -> Dict[str, int]:
        """Get timeout settings"""
        return self.config.get("timeouts", {"navigation": 30000, "element": 10000})
    
    def get_cookie_path(self) -> str:
        """Get path for storing cookies"""
        return f"cookies_{self.name}.json"
    
    # ===========================================
    # REQUIRED: Subclasses must implement these
    # ===========================================
    
    @abstractmethod
    async def login(self, username: str, password: str) -> bool:
        """
        Perform site-specific login.
        
        Returns:
            True if login successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def search(self, criteria: SearchCriteria) -> bool:
        """
        Fill and submit search form.
        
        Returns:
            True if search submitted successfully
        """
        pass
    
    @abstractmethod
    async def has_next_page(self) -> bool:
        """Check if there are more result pages"""
        pass
    
    @abstractmethod
    async def go_next_page(self) -> bool:
        """
        Navigate to next results page.
        
        Returns:
            True if navigation successful
        """
        pass
    
    @abstractmethod
    def get_listing_url(self, listing_id: str) -> str:
        """Build detail page URL from listing ID"""
        pass
    
    # ===========================================
    # OPTIONAL: Override these for customization
    # ===========================================
    
    async def pre_login_hook(self):
        """
        Called before login attempt.
        Override to handle popups, cookie banners, etc.
        """
        pass
    
    async def post_login_hook(self):
        """
        Called after successful login.
        Override for post-login setup.
        """
        pass
    
    async def pre_search_hook(self):
        """
        Called before search.
        Override to clear filters, navigate to search page, etc.
        """
        pass
    
    async def post_search_hook(self):
        """
        Called after search submitted.
        Override for any post-search handling.
        """
        pass
    
    async def is_logged_in(self) -> bool:
        """
        Check if currently logged in.
        Override with site-specific check.
        """
        indicator = self.selectors.get("login", {}).get("success_indicator")
        if indicator:
            return await self.browser.is_visible(indicator)
        return False
    
    async def extract_listings_from_html(self, html: str) -> Optional[List[Dict]]:
        """
        Site-specific listing extraction.
        
        Override if you want to use DOM parsing instead of AI extraction.
        Return None to use default AI extraction.
        
        Returns:
            List of raw listing dicts, or None to use AI
        """
        return None
    
    async def extract_detail_from_html(self, html: str, listing_id: str) -> Optional[Dict]:
        """
        Site-specific detail extraction.
        
        Override for custom extraction logic.
        Return None to use default AI extraction.
        """
        return None
    
    def transform_listing(self, raw: Dict) -> Dict:
        """
        Transform raw extracted data to match CarListing schema.
        
        Override to handle site-specific field mappings.
        Called after extraction, before creating Pydantic model.
        
        Args:
            raw: Raw dict from extraction
            
        Returns:
            Transformed dict matching CarListing fields
        """
        return raw
    
    def transform_detail(self, raw: Dict) -> Dict:
        """
        Transform raw detail data to match CarDetail schema.
        """
        return raw
    
    def get_extraction_hints(self) -> Dict[str, str]:
        """
        Return hints to help AI extraction.
        
        Override to provide site-specific guidance for the AI extractor.
        """
        return {
            "site_name": self.name,
            "id_field_name": "lot number",
            "price_field_name": "current bid",
        }
```

---

## Step 4: Create Copart Adapter

### sites/copart/adapter.py

Refactor the existing Copart logic into an adapter:

```python
from typing import Dict, Optional
from core.base_adapter import SiteAdapter
from core.models import SearchCriteria


class CopartAdapter(SiteAdapter):
    """
    Adapter for Copart auction site.
    """
    
    name = "copart"
    
    async def login(self, username: str, password: str) -> bool:
        """Copart login flow"""
        sel = self.selectors["login"]
        
        await self.browser.goto(self.urls["login"])
        await self.browser.delay()
        
        await self.browser.fill(sel["username"], username)
        await self.browser.delay()
        await self.browser.fill(sel["password"], password)
        await self.browser.delay()
        
        await self.browser.click(sel["submit"])
        
        try:
            success = await self.browser.wait_for_selector(
                sel["success_indicator"],
                timeout=15000
            )
            return success
        except:
            return False
    
    async def search(self, criteria: SearchCriteria) -> bool:
        """Copart search with typeahead dropdowns"""
        sel = self.selectors["search"]
        
        await self.browser.goto(self.urls["search"])
        await self.browser.delay()
        
        # Make - uses typeahead dropdown
        if criteria.make:
            await self.browser.fill(sel["make_input"], criteria.make)
            await self.browser.delay()
            try:
                await self.browser.wait_for_selector(sel["make_dropdown"], timeout=5000)
                await self.browser.keyboard_press("ArrowDown")
                await self.browser.keyboard_press("Enter")
                await self.browser.delay()
            except:
                print("Make dropdown not found, continuing...")
        
        # Model - uses typeahead dropdown
        if criteria.model:
            await self.browser.fill(sel["model_input"], criteria.model)
            await self.browser.delay()
            try:
                await self.browser.wait_for_selector(sel["model_dropdown"], timeout=5000)
                await self.browser.keyboard_press("ArrowDown")
                await self.browser.keyboard_press("Enter")
                await self.browser.delay()
            except:
                print("Model dropdown not found, continuing...")
        
        # Year range - standard select dropdowns
        if criteria.year_min:
            await self.browser.select(sel["year_from"], str(criteria.year_min))
            await self.browser.delay()
            
        if criteria.year_max:
            await self.browser.select(sel["year_to"], str(criteria.year_max))
            await self.browser.delay()
        
        # Submit
        await self.browser.click(sel["search_button"])
        await self.browser.wait_for_network_idle()
        
        return True
    
    async def has_next_page(self) -> bool:
        """Check Copart pagination"""
        sel = self.selectors["results"]["pagination_next"]
        element = await self.browser.query_selector(sel)
        
        if not element:
            return False
            
        # Copart disables via class
        classes = await element.get_attribute("class") or ""
        is_disabled = await element.get_attribute("disabled")
        
        return not is_disabled and "disabled" not in classes
    
    async def go_next_page(self) -> bool:
        """Navigate to next Copart results page"""
        if not await self.has_next_page():
            return False
            
        sel = self.selectors["results"]["pagination_next"]
        await self.browser.click(sel)
        await self.browser.delay()
        await self.browser.wait_for_network_idle()
        
        return True
    
    def get_listing_url(self, listing_id: str) -> str:
        """Build Copart lot URL"""
        return f"https://www.copart.com/lot/{listing_id}"
    
    def get_extraction_hints(self) -> Dict[str, str]:
        """Copart-specific extraction hints"""
        return {
            "site_name": "Copart",
            "id_field_name": "lot number",
            "price_field_name": "current bid",
            "additional_notes": "Lot numbers are 8 digits. URLs follow pattern /lot/{lot_number}",
        }
```

### sites/copart/__init__.py

```python
from .adapter import CopartAdapter

__all__ = ["CopartAdapter"]
```

---

## Step 5: Create IAAI Adapter Template

### sites/iaai/config.yaml

```yaml
site: iaai
base_url: https://www.iaai.com

urls:
  login: https://www.iaai.com/Login
  search: https://www.iaai.com/Search
  detail_template: https://www.iaai.com/Vehicle?itemID={id}

selectors:
  login:
    sign_in_button: "#signInButton, .sign-in-link"
    username: "#Email, #username"
    password: "#Password, #password"
    submit: "#LoginButton, button[type='submit']"
    error_message: ".validation-summary-errors, .login-error"
    success_indicator: ".user-name, .logged-in-user, #userMenu"
    
  search:
    make_dropdown: "#MakeDropdown, [data-field='make']"
    make_option: "[data-make='{value}']"
    model_dropdown: "#ModelDropdown, [data-field='model']"
    model_option: "[data-model='{value}']"
    year_from: "#YearFrom, [data-field='yearMin']"
    year_to: "#YearTo, [data-field='yearMax']"
    search_button: "#SearchButton, .search-submit"
    clear_filters: ".clear-filters, #ClearSearch"
    
  results:
    listing_row: ".search-result-item, .vehicle-row, [data-item-id]"
    item_id: "[data-item-id], .stock-number"
    vehicle_info: ".vehicle-info, .vehicle-details"
    current_bid: ".current-bid, .high-bid"
    buy_now: ".buy-now-price"
    odometer: ".odometer, .mileage"
    damage_type: ".primary-damage, .damage-info"
    location: ".branch-name, .location"
    sale_date: ".sale-date, .auction-date"
    thumbnail: ".vehicle-image img"
    no_results: ".no-results, .empty-search"
    pagination_next: ".pagination-next:not(.disabled), .next-page:not(.disabled)"
    pagination_info: ".pagination-info, .results-count"
    
  detail:
    title: "h1, .vehicle-title"
    stock_number: ".stock-number, [data-stock]"
    vin: ".vin, [data-vin]"
    odometer: ".odometer-value"
    engine: ".engine-info"
    transmission: ".transmission"
    drive_type: ".drive-type"
    fuel_type: ".fuel-type"
    color: ".exterior-color"
    interior_color: ".interior-color"
    keys: ".keys-info"
    airbags: ".airbags"
    primary_damage: ".primary-damage"
    secondary_damage: ".secondary-damage"
    seller: ".seller-info"
    title_type: ".title-type, .title-status"
    sale_date: ".sale-date"
    location: ".branch-location"
    current_bid: ".current-bid"
    buy_now: ".buy-now"
    images: ".gallery img, .vehicle-images img"
    description: ".vehicle-description"

timeouts:
  navigation: 30000
  element: 10000
  page_load: 60000

rate_limit:
  min_delay_ms: 2500
  max_delay_ms: 6000
```

### sites/iaai/adapter.py

```python
from typing import Dict, Optional
from core.base_adapter import SiteAdapter
from core.models import SearchCriteria


class IAAIAdapter(SiteAdapter):
    """
    Adapter for IAAI (Insurance Auto Auctions) site.
    """
    
    name = "iaai"
    
    async def pre_login_hook(self):
        """IAAI may show cookie consent popup"""
        try:
            cookie_accept = await self.browser.query_selector(".cookie-accept, #acceptCookies")
            if cookie_accept:
                await self.browser.click(".cookie-accept, #acceptCookies")
                await self.browser.delay()
        except:
            pass
    
    async def login(self, username: str, password: str) -> bool:
        """IAAI login flow"""
        sel = self.selectors["login"]
        
        await self.browser.goto(self.urls["login"])
        await self.browser.delay()
        
        # IAAI might have a sign-in button before form appears
        try:
            await self.browser.click(sel["sign_in_button"], timeout=3000)
            await self.browser.delay()
        except:
            pass  # Form might already be visible
        
        await self.browser.fill(sel["username"], username)
        await self.browser.delay()
        await self.browser.fill(sel["password"], password)
        await self.browser.delay()
        
        await self.browser.click(sel["submit"])
        
        try:
            return await self.browser.wait_for_selector(
                sel["success_indicator"],
                timeout=15000
            )
        except:
            return False
    
    async def search(self, criteria: SearchCriteria) -> bool:
        """IAAI search form"""
        sel = self.selectors["search"]
        
        await self.browser.goto(self.urls["search"])
        await self.browser.delay()
        
        # IAAI uses click-to-select dropdowns
        if criteria.make:
            await self.browser.click(sel["make_dropdown"])
            await self.browser.delay()
            # Click the specific make option
            make_selector = sel["make_option"].format(value=criteria.make)
            await self.browser.click(make_selector)
            await self.browser.delay()
        
        if criteria.model:
            await self.browser.click(sel["model_dropdown"])
            await self.browser.delay()
            model_selector = sel["model_option"].format(value=criteria.model)
            await self.browser.click(model_selector)
            await self.browser.delay()
        
        if criteria.year_min:
            await self.browser.select(sel["year_from"], str(criteria.year_min))
            await self.browser.delay()
            
        if criteria.year_max:
            await self.browser.select(sel["year_to"], str(criteria.year_max))
            await self.browser.delay()
        
        await self.browser.click(sel["search_button"])
        await self.browser.wait_for_network_idle()
        
        return True
    
    async def has_next_page(self) -> bool:
        """Check IAAI pagination"""
        sel = self.selectors["results"]["pagination_next"]
        return await self.browser.is_visible(sel)
    
    async def go_next_page(self) -> bool:
        """Navigate to next IAAI results page"""
        sel = self.selectors["results"]["pagination_next"]
        
        if not await self.has_next_page():
            return False
            
        await self.browser.click(sel)
        await self.browser.delay()
        await self.browser.wait_for_network_idle()
        
        return True
    
    def get_listing_url(self, listing_id: str) -> str:
        """Build IAAI vehicle URL"""
        return f"https://www.iaai.com/Vehicle?itemID={listing_id}"
    
    def transform_listing(self, raw: Dict) -> Dict:
        """Transform IAAI field names to standard schema"""
        transformed = raw.copy()
        
        # IAAI uses "stock_number" instead of "id"
        if "stock_number" in transformed and "id" not in transformed:
            transformed["id"] = transformed.pop("stock_number")
        
        # IAAI uses "item_id" in some places
        if "item_id" in transformed and "id" not in transformed:
            transformed["id"] = transformed.pop("item_id")
            
        # IAAI calls it "primary_damage"
        if "primary_damage" in transformed and "damage_type" not in transformed:
            transformed["damage_type"] = transformed.pop("primary_damage")
            
        # IAAI uses "mileage" not "miles"
        if "mileage" in transformed and "miles" not in transformed:
            transformed["miles"] = transformed.pop("mileage")
            
        # IAAI uses "high_bid" not "current_bid"
        if "high_bid" in transformed and "current_bid" not in transformed:
            transformed["current_bid"] = transformed.pop("high_bid")
        
        return transformed
    
    def get_extraction_hints(self) -> Dict[str, str]:
        """IAAI-specific extraction hints"""
        return {
            "site_name": "IAAI",
            "id_field_name": "stock number or item ID",
            "price_field_name": "high bid or current bid",
            "additional_notes": (
                "IAAI uses 'stock number' for listing IDs. "
                "URLs use itemID parameter. "
                "Mileage may be labeled as 'odometer'."
            ),
        }
```

### sites/iaai/__init__.py

```python
from .adapter import IAAIAdapter

__all__ = ["IAAIAdapter"]
```

---

## Step 6: Update Extractor for Multi-Site

### core/extractor.py

Add support for site-specific hints:

```python
import json
import re
from typing import Dict, List, Optional

import anthropic

from .models import CarListing, CarDetail


class ListingExtractor:
    """
    AI-powered extraction of car listing data.
    Supports multiple sites via extraction hints.
    """
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
    def _truncate_html(self, html: str, max_chars: int = 50000) -> str:
        """Truncate HTML while preserving structure"""
        if len(html) <= max_chars:
            return html
        truncated = html[:max_chars]
        last_close = truncated.rfind(">")
        if last_close > max_chars - 2000:
            truncated = truncated[:last_close + 1]
        return truncated + "\n<!-- truncated -->"
        
    def _clean_json_response(self, response_text: str) -> str:
        """Extract JSON from response"""
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        return text.strip()
    
    async def extract_listings(
        self, 
        html: str, 
        site: str = "unknown",
        hints: Dict[str, str] = None
    ) -> List[Dict]:
        """
        Extract listings from search results HTML.
        
        Args:
            html: Page HTML
            site: Site name for context
            hints: Site-specific extraction hints
            
        Returns:
            List of raw dicts (not models, for adapter transformation)
        """
        hints = hints or {}
        truncated_html = self._truncate_html(html)
        
        id_field = hints.get("id_field_name", "lot number or ID")
        price_field = hints.get("price_field_name", "current bid")
        additional = hints.get("additional_notes", "")
        
        prompt = f"""Extract car listings from this {site} auction search results page.

{f"SITE-SPECIFIC NOTES: {additional}" if additional else ""}

HTML CONTENT:
{truncated_html}

For each listing, extract:
- id: The {id_field} (REQUIRED)
- url: Link to detail page
- year: Model year (integer)
- make: Manufacturer
- model: Model name
- trim: Trim level
- miles: Odometer (integer, no commas)
- current_bid: {price_field} (integer, no $ or commas)
- buy_now_price: Buy now price if available
- condition: Vehicle condition
- damage_type: Primary damage
- secondary_damage: Secondary damage
- location: Yard/city
- sale_date: Auction date (ISO format)
- thumbnail_url: Image URL

Return ONLY a JSON array. No explanations.
Use null for missing fields.
If no listings found, return: []
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text
        cleaned_json = self._clean_json_response(response_text)
        
        try:
            return json.loads(cleaned_json)
        except json.JSONDecodeError:
            print(f"Failed to parse listings JSON")
            return []
    
    async def extract_detail(
        self,
        html: str,
        listing_id: str,
        site: str = "unknown",
        hints: Dict[str, str] = None
    ) -> Optional[Dict]:
        """
        Extract full details from listing detail page.
        
        Returns:
            Raw dict or None on failure
        """
        hints = hints or {}
        truncated_html = self._truncate_html(html, max_chars=40000)
        
        additional = hints.get("additional_notes", "")
        
        prompt = f"""Extract vehicle details from this {site} auction listing page.

{f"SITE-SPECIFIC NOTES: {additional}" if additional else ""}

HTML CONTENT:
{truncated_html}

Extract all available fields:
- id: Use "{listing_id}" if not found
- year, make, model, trim
- miles: Odometer (integer)
- current_bid, buy_now_price (integers)
- condition, damage_type, secondary_damage
- location, sale_date
- vin: 17-character VIN
- engine, transmission, drive_type, fuel_type
- color, interior_color
- keys: Yes/No/Unknown
- airbags
- seller
- title_type: Clean/Salvage/Rebuilt/etc.
- images: Array of image URLs
- description

Return ONLY a JSON object. Use null for missing fields.
"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text
        cleaned_json = self._clean_json_response(response_text)
        
        try:
            return json.loads(cleaned_json)
        except json.JSONDecodeError:
            print(f"Failed to parse detail JSON for {listing_id}")
            return None
```

---

## Step 7: Create Unified Workflow

### core/workflow.py

```python
from typing import Dict, List, Optional, Type
from datetime import datetime

from .base_adapter import SiteAdapter
from .browser import BaseBrowser
from .extractor import ListingExtractor
from .storage import Storage
from .models import SearchCriteria, CarListing, CarDetail


class ScrapeWorkflow:
    """
    Unified scraping workflow that works with any site adapter.
    
    Handles:
    - Browser lifecycle
    - Session management (cookies)
    - Login flow
    - Search and pagination
    - Extraction (via adapter or AI)
    - Storage
    """
    
    def __init__(
        self,
        adapter: SiteAdapter,
        extractor: ListingExtractor,
        storage: Storage,
    ):
        self.adapter = adapter
        self.extractor = extractor
        self.storage = storage
        self.browser: Optional[BaseBrowser] = None
        
    async def setup(self, headless: bool = True):
        """Initialize browser and inject into adapter"""
        self.browser = BaseBrowser(
            rate_limit=self.adapter.rate_limit,
            timeouts=self.adapter.timeouts
        )
        await self.browser.start(headless=headless)
        self.adapter.set_browser(self.browser)
        
    async def teardown(self):
        """Clean up resources"""
        if self.browser:
            await self.browser.close()
            
    async def ensure_logged_in(self, credentials: Dict[str, str]) -> bool:
        """
        Ensure we have a valid session.
        Tries saved cookies first, then fresh login.
        """
        cookie_path = self.adapter.get_cookie_path()
        
        # Try loading saved session
        if await self.browser.load_cookies(cookie_path):
            # Verify session is still valid
            await self.browser.goto(self.adapter.urls.get("search", self.adapter.urls["login"]))
            if await self.adapter.is_logged_in():
                print(f"[{self.adapter.name}] Using saved session")
                return True
        
        # Fresh login
        print(f"[{self.adapter.name}] Logging in...")
        await self.adapter.pre_login_hook()
        
        success = await self.adapter.login(
            credentials["username"],
            credentials["password"]
        )
        
        if success:
            await self.adapter.post_login_hook()
            await self.browser.save_cookies(cookie_path)
            print(f"[{self.adapter.name}] Login successful")
            return True
        else:
            print(f"[{self.adapter.name}] Login failed")
            return False
    
    async def run_search(
        self,
        credentials: Dict[str, str],
        criteria: SearchCriteria,
        max_pages: int = 10,
        save_to_db: bool = True
    ) -> Dict:
        """
        Execute full search workflow.
        
        Returns:
            Stats dict with listings_count, pages, errors
        """
        stats = {
            "site": self.adapter.name,
            "listings": 0,
            "pages": 0,
            "errors": 0,
            "started_at": datetime.utcnow().isoformat()
        }
        
        # Login
        if not await self.ensure_logged_in(credentials):
            stats["errors"] = 1
            stats["error_message"] = "Login failed"
            return stats
        
        # Search
        print(f"[{self.adapter.name}] Searching for {criteria.make} {criteria.model or ''}")
        await self.adapter.pre_search_hook()
        await self.adapter.search(criteria)
        await self.adapter.post_search_hook()
        
        # Paginate and extract
        page = 1
        all_listings = []
        
        while page <= max_pages:
            print(f"[{self.adapter.name}] Processing page {page}...")
            
            try:
                html = await self.browser.get_html()
                
                # Try site-specific extraction first
                raw_listings = await self.adapter.extract_listings_from_html(html)
                
                # Fall back to AI extraction
                if raw_listings is None:
                    raw_listings = await self.extractor.extract_listings(
                        html,
                        site=self.adapter.name,
                        hints=self.adapter.get_extraction_hints()
                    )
                
                if not raw_listings:
                    print(f"[{self.adapter.name}] No listings found on page {page}")
                    if page == 1:
                        print(f"[{self.adapter.name}] Search may have returned no results")
                    break
                
                # Transform and create models
                listings = []
                for raw in raw_listings:
                    try:
                        transformed = self.adapter.transform_listing(raw)
                        transformed["source_site"] = self.adapter.name
                        listing = CarListing(**transformed)
                        listings.append(listing)
                    except Exception as e:
                        print(f"[{self.adapter.name}] Skipping invalid listing: {e}")
                        continue
                
                all_listings.extend(listings)
                stats["listings"] += len(listings)
                stats["pages"] = page
                
                print(f"[{self.adapter.name}] Extracted {len(listings)} listings from page {page}")
                
                # Save incrementally
                if save_to_db and listings:
                    await self.storage.upsert_listings(listings)
                    
            except Exception as e:
                print(f"[{self.adapter.name}] Error on page {page}: {e}")
                stats["errors"] += 1
                if stats["errors"] >= 3:
                    print(f"[{self.adapter.name}] Too many errors, stopping")
                    break
            
            # Next page
            if not await self.adapter.has_next_page():
                print(f"[{self.adapter.name}] No more pages")
                break
                
            await self.adapter.go_next_page()
            page += 1
        
        stats["completed_at"] = datetime.utcnow().isoformat()
        return stats
    
    async def fetch_details(
        self,
        credentials: Dict[str, str],
        listings: List[CarListing],
        save_to_db: bool = True
    ) -> Dict:
        """
        Fetch full details for a list of listings.
        
        Returns:
            Stats dict
        """
        stats = {
            "site": self.adapter.name,
            "processed": 0,
            "success": 0,
            "errors": 0
        }
        
        if not listings:
            return stats
            
        # Login
        if not await self.ensure_logged_in(credentials):
            stats["error_message"] = "Login failed"
            return stats
        
        for i, listing in enumerate(listings, 1):
            print(f"[{self.adapter.name}] Fetching detail {i}/{len(listings)}: {listing.id}")
            stats["processed"] += 1
            
            try:
                url = listing.url or self.adapter.get_listing_url(listing.id)
                html = await self.browser.goto(url)
                if not html:
                    html = await self.browser.get_html()
                
                await self.browser.delay()
                html = await self.browser.get_html()
                
                # Try site-specific extraction
                raw_detail = await self.adapter.extract_detail_from_html(html, listing.id)
                
                # Fall back to AI
                if raw_detail is None:
                    raw_detail = await self.extractor.extract_detail(
                        html,
                        listing.id,
                        site=self.adapter.name,
                        hints=self.adapter.get_extraction_hints()
                    )
                
                if raw_detail:
                    transformed = self.adapter.transform_detail(raw_detail)
                    transformed["source_site"] = self.adapter.name
                    transformed["id"] = listing.id
                    
                    detail = CarDetail(**transformed)
                    
                    if save_to_db:
                        await self.storage.upsert_detail(detail)
                    
                    stats["success"] += 1
                    print(f"[{self.adapter.name}] Got detail for {detail.year} {detail.make} {detail.model}")
                else:
                    stats["errors"] += 1
                    print(f"[{self.adapter.name}] Failed to extract detail for {listing.id}")
                    
            except Exception as e:
                stats["errors"] += 1
                print(f"[{self.adapter.name}] Error fetching {listing.id}: {e}")
                continue
        
        return stats
```

---

## Step 8: Create Unified CLI

### cli/main.py

```python
import asyncio
import os
from typing import Dict

import click
from dotenv import load_dotenv

from core import (
    SearchCriteria,
    Storage,
    ListingExtractor,
    ScrapeWorkflow,
)
from sites.copart import CopartAdapter
from sites.iaai import IAAIAdapter

load_dotenv()

# Registry of available site adapters
ADAPTERS = {
    "copart": CopartAdapter,
    "iaai": IAAIAdapter,
}


def get_credentials(site: str) -> Dict[str, str]:
    """Get credentials for a site from environment"""
    site_upper = site.upper()
    return {
        "username": os.environ.get(f"{site_upper}_USERNAME"),
        "password": os.environ.get(f"{site_upper}_PASSWORD"),
    }


def get_database_url() -> str:
    return os.environ["DATABASE_URL"]


def get_anthropic_key() -> str:
    return os.environ["ANTHROPIC_API_KEY"]


@click.group()
def cli():
    """Multi-site Auction Car Scraper"""
    pass


@cli.command()
def init_db():
    """Initialize database schema"""
    async def _init():
        storage = Storage(get_database_url())
        await storage.connect()
        await storage.init_schema()
        await storage.close()
        click.echo("✅ Database initialized!")
    asyncio.run(_init())


@cli.command()
@click.option("--site", type=click.Choice(list(ADAPTERS.keys())), required=True)
@click.option("--make", required=True)
@click.option("--model", default=None)
@click.option("--year-min", type=int, default=None)
@click.option("--year-max", type=int, default=None)
@click.option("--max-pages", type=int, default=10)
@click.option("--headless/--no-headless", default=True)
def search(site, make, model, year_min, year_max, max_pages, headless):
    """Search a specific auction site"""
    criteria = SearchCriteria(
        make=make,
        model=model,
        year_min=year_min,
        year_max=year_max
    )
    asyncio.run(_search(site, criteria, max_pages, headless))


async def _search(site: str, criteria: SearchCriteria, max_pages: int, headless: bool):
    # Initialize
    adapter = ADAPTERS[site]()
    extractor = ListingExtractor(get_anthropic_key())
    storage = Storage(get_database_url())
    
    await storage.connect()
    
    workflow = ScrapeWorkflow(adapter, extractor, storage)
    await workflow.setup(headless=headless)
    
    try:
        stats = await workflow.run_search(
            credentials=get_credentials(site),
            criteria=criteria,
            max_pages=max_pages
        )
        
        click.echo(f"\n{'='*50}")
        click.echo(f"✅ {site.upper()} search complete!")
        click.echo(f"   Listings: {stats['listings']}")
        click.echo(f"   Pages: {stats['pages']}")
        click.echo(f"   Errors: {stats['errors']}")
        click.echo(f"{'='*50}\n")
        
    finally:
        await workflow.teardown()
        await storage.close()


@cli.command()
@click.option("--site", type=click.Choice(list(ADAPTERS.keys())), required=True)
@click.option("--limit", type=int, default=50)
@click.option("--headless/--no-headless", default=True)
def fetch_details(site, limit, headless):
    """Fetch details for listings missing them"""
    asyncio.run(_fetch_details(site, limit, headless))


async def _fetch_details(site: str, limit: int, headless: bool):
    adapter = ADAPTERS[site]()
    extractor = ListingExtractor(get_anthropic_key())
    storage = Storage(get_database_url())
    
    await storage.connect()
    
    # Get listings needing details for this site
    listings = await storage.get_listings_without_details(limit=limit, site=site)
    
    if not listings:
        click.echo(f"✅ All {site} listings have details!")
        await storage.close()
        return
    
    click.echo(f"Found {len(listings)} {site} listings needing details")
    
    workflow = ScrapeWorkflow(adapter, extractor, storage)
    await workflow.setup(headless=headless)
    
    try:
        stats = await workflow.fetch_details(
            credentials=get_credentials(site),
            listings=listings
        )
        
        click.echo(f"\n✅ Detail fetch complete!")
        click.echo(f"   Processed: {stats['processed']}")
        click.echo(f"   Success: {stats['success']}")
        click.echo(f"   Errors: {stats['errors']}")
        
    finally:
        await workflow.teardown()
        await storage.close()


@cli.command()
@click.option("--make", required=True)
@click.option("--model", default=None)
@click.option("--year-min", type=int, default=None)
@click.option("--year-max", type=int, default=None)
@click.option("--max-pages", type=int, default=10)
@click.option("--headless/--no-headless", default=True)
def search_all(make, model, year_min, year_max, max_pages, headless):
    """Search ALL supported auction sites"""
    criteria = SearchCriteria(
        make=make,
        model=model,
        year_min=year_min,
        year_max=year_max
    )
    asyncio.run(_search_all(criteria, max_pages, headless))


async def _search_all(criteria: SearchCriteria, max_pages: int, headless: bool):
    """Search all sites sequentially"""
    extractor = ListingExtractor(get_anthropic_key())
    storage = Storage(get_database_url())
    await storage.connect()
    
    all_stats = {}
    
    for site_name, adapter_class in ADAPTERS.items():
        click.echo(f"\n{'='*50}")
        click.echo(f"🔍 Searching {site_name.upper()}...")
        click.echo(f"{'='*50}")
        
        adapter = adapter_class()
        workflow = ScrapeWorkflow(adapter, extractor, storage)
        await workflow.setup(headless=headless)
        
        try:
            stats = await workflow.run_search(
                credentials=get_credentials(site_name),
                criteria=criteria,
                max_pages=max_pages
            )
            all_stats[site_name] = stats
        except Exception as e:
            click.echo(f"❌ Error searching {site_name}: {e}")
            all_stats[site_name] = {"error": str(e)}
        finally:
            await workflow.teardown()
    
    await storage.close()
    
    # Summary
    click.echo(f"\n{'='*50}")
    click.echo("📊 SEARCH SUMMARY")
    click.echo(f"{'='*50}")
    total_listings = 0
    for site, stats in all_stats.items():
        count = stats.get("listings", 0)
        total_listings += count
        click.echo(f"   {site}: {count} listings")
    click.echo(f"   TOTAL: {total_listings} listings")
    click.echo(f"{'='*50}\n")


@cli.command()
def list_sites():
    """List all supported auction sites"""
    click.echo("\n📋 Supported sites:")
    for site in ADAPTERS.keys():
        click.echo(f"   - {site}")
    click.echo("")


if __name__ == "__main__":
    cli()
```

---

## Step 9: Update Storage for Multi-Site Queries

Add site filtering to storage methods:

### core/storage.py (additions)

```python
# Add to existing Storage class:

async def get_listings_without_details(
    self, 
    limit: int = 50, 
    site: str = None
) -> List[CarListing]:
    """Get listings without details, optionally filtered by site"""
    query = """
        SELECT l.* 
        FROM scraper.listings l
        LEFT JOIN scraper.details d 
            ON l.id = d.id AND l.source_site = d.source_site
        WHERE d.id IS NULL
    """
    params = []
    
    if site:
        query += " AND l.source_site = $1"
        params.append(site)
        query += f" ORDER BY l.scraped_at DESC LIMIT ${len(params) + 1}"
        params.append(limit)
    else:
        query += " ORDER BY l.scraped_at DESC LIMIT $1"
        params.append(limit)
    
    async with self.pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [CarListing(**dict(row)) for row in rows]

async def get_stats_by_site(self) -> Dict[str, Dict]:
    """Get statistics broken down by site"""
    async with self.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                source_site,
                COUNT(*) as total_listings,
                COUNT(DISTINCT make) as unique_makes,
                MIN(scraped_at) as first_scraped,
                MAX(scraped_at) as last_scraped
            FROM scraper.listings
            GROUP BY source_site
        """)
        
        stats = {}
        for row in rows:
            site = row["source_site"]
            detail_count = await conn.fetchval(
                "SELECT COUNT(*) FROM scraper.details WHERE source_site = $1",
                site
            )
            stats[site] = {
                "total_listings": row["total_listings"],
                "unique_makes": row["unique_makes"],
                "details_fetched": detail_count,
                "first_scraped": row["first_scraped"],
                "last_scraped": row["last_scraped"]
            }
        
        return stats
```

---

## Step 10: Update Environment Variables

### .env.example (multi-site version)

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# AI
ANTHROPIC_API_KEY=sk-ant-...

# Copart credentials
COPART_USERNAME=your_copart_username
COPART_PASSWORD=your_copart_password

# IAAI credentials
IAAI_USERNAME=your_iaai_username
IAAI_PASSWORD=your_iaai_password

# Manheim credentials (future)
# MANHEIM_USERNAME=
# MANHEIM_PASSWORD=
```

---

## Adding a New Site Checklist

When adding a third site (e.g., Manheim), follow these steps:

### 1. Create site directory
```bash
mkdir -p sites/manheim
touch sites/manheim/__init__.py
```

### 2. Create config.yaml
- Copy from an existing site as template
- Update URLs and selectors by inspecting the actual site
- Adjust rate limits as needed

### 3. Create adapter.py
- Inherit from `SiteAdapter`
- Implement required methods: `login`, `search`, `has_next_page`, `go_next_page`, `get_listing_url`
- Override optional methods as needed for site quirks
- Add `transform_listing` if field names differ

### 4. Register adapter
```python
# In cli/main.py
from sites.manheim import ManheimAdapter

ADAPTERS = {
    "copart": CopartAdapter,
    "iaai": IAAIAdapter,
    "manheim": ManheimAdapter,  # Add this
}
```

### 5. Add credentials
```bash
# In .env
MANHEIM_USERNAME=...
MANHEIM_PASSWORD=...
```

### 6. Test
```bash
python -m cli.main search --site manheim --make Honda --max-pages 2 --no-headless
```

---

## Migration Checklist

- [ ] Create new directory structure
- [ ] Move/rename files to core/
- [ ] Create base_adapter.py
- [ ] Refactor CopartAdapter from existing browser.py
- [ ] Update extractor for multi-site hints
- [ ] Create workflow.py
- [ ] Update CLI for multi-site
- [ ] Update storage for site filtering
- [ ] Update .env with per-site credentials
- [ ] Test Copart still works
- [ ] Add IAAI adapter
- [ ] Test IAAI
- [ ] Add search-all command
- [ ] Update render.yaml for multi-site

---

## Estimated Time

| Task | Time |
|------|------|
| Restructure directories | 15 min |
| Create base classes | 30 min |
| Refactor Copart adapter | 30 min |
| Update extractor/storage | 20 min |
| Create unified CLI | 30 min |
| Test existing functionality | 30 min |
| Add IAAI adapter | 1-2 hours |
| Test and debug | 1 hour |
| **Total** | **4-5 hours** |

---

## Notes

- The single-site version you're building now is designed to make this migration straightforward
- All the core logic (extraction, storage, models) stays the same
- You're mainly just reorganizing code and adding the adapter abstraction
- Don't migrate until you actually need site #2 - premature abstraction is worse than duplication
