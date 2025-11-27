# Auction Car Scraper - Build Instructions for Claude Code

## Overview

Build a Python scraper for auction car websites (starting with Copart). The system should:
1. Login to the auction site
2. Search for cars matching criteria (make/model/year/miles)
3. Extract listing data using AI
4. Store results in PostgreSQL
5. Optionally fetch full details for each listing

**Architecture:** Deterministic browser automation (Playwright) + AI extraction (Claude API). No complex multi-agent orchestration - keep it simple.

**Key Constraints:**
- Site rarely changes layouts → Hardcode selectors
- Batch processing is fine → No real-time requirements  
- Budget: ~$150/month for AI → Be efficient with API calls
- One site initially → No premature abstraction

---

## Project Structure

Create this exact structure:

```
/auction-scraper
  /config
    __init__.py
    settings.py         # Environment and config loading
    copart.yaml         # Selectors and URLs for Copart
  /scraper
    __init__.py
    browser.py          # Playwright wrapper
    extractor.py        # AI extraction using Claude
    storage.py          # PostgreSQL operations
  /models
    __init__.py
    schemas.py          # Pydantic models
  main.py               # CLI entry point
  requirements.txt
  render.yaml           # Render deployment config
  .env.example
  README.md
```

---

## Step 1: Requirements and Environment

### requirements.txt

```
playwright==1.40.0
anthropic==0.18.0
asyncpg==0.29.0
pydantic==2.5.0
pyyaml==6.0.1
click==8.1.7
python-dotenv==1.0.0
```

### .env.example

```
DATABASE_URL=postgresql://user:pass@host:5432/dbname
ANTHROPIC_API_KEY=sk-ant-...
COPART_USERNAME=your_username
COPART_PASSWORD=your_password
```

---

## Step 2: Data Models

### /models/schemas.py

```python
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
import re


class SearchCriteria(BaseModel):
    """Search parameters for finding cars"""
    make: str
    model: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    max_miles: Optional[int] = None
    max_price: Optional[int] = None
    
    @field_validator('year_min', 'year_max')
    @classmethod
    def validate_year(cls, v):
        if v is not None and (v < 1900 or v > datetime.now().year + 1):
            raise ValueError(f'Year must be between 1900 and {datetime.now().year + 1}')
        return v
    
    @field_validator('max_miles', 'max_price')
    @classmethod
    def validate_positive(cls, v):
        if v is not None and v < 0:
            raise ValueError('Value must be non-negative')
        return v


class CarListing(BaseModel):
    """Basic car listing from search results"""
    id: str
    source_site: str = "copart"
    url: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    miles: Optional[int] = None
    current_bid: Optional[int] = None
    buy_now_price: Optional[int] = None
    condition: Optional[str] = None
    damage_type: Optional[str] = None
    secondary_damage: Optional[str] = None
    location: Optional[str] = None
    sale_date: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator('year')
    @classmethod
    def validate_year(cls, v):
        if v is not None and (v < 1900 or v > datetime.now().year + 1):
            return None  # Invalid year, set to None rather than fail
        return v


class CarDetail(CarListing):
    """Full car details from detail page"""
    vin: Optional[str] = None
    engine: Optional[str] = None
    transmission: Optional[str] = None
    drive_type: Optional[str] = None
    fuel_type: Optional[str] = None
    color: Optional[str] = None
    interior_color: Optional[str] = None
    keys: Optional[str] = None
    airbags: Optional[str] = None
    seller: Optional[str] = None
    title_type: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    description: Optional[str] = None

    @field_validator('vin')
    @classmethod
    def validate_vin(cls, v):
        if v is not None:
            v = v.strip().upper()
            # VIN should be 17 alphanumeric characters (no I, O, Q)
            if len(v) != 17 or not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', v):
                return None  # Invalid VIN, set to None
        return v


class ScrapeRun(BaseModel):
    """Record of a scraping run"""
    id: Optional[int] = None
    site: str
    criteria: SearchCriteria
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    listings_found: int = 0
    details_fetched: int = 0
    errors: int = 0
    status: str = "running"
```

---

## Step 3: Site Configuration

### /config/copart.yaml

```yaml
site: copart
base_url: https://www.copart.com

urls:
  login: https://www.copart.com/login
  search: https://www.copart.com/vehicleFinderSearch
  
selectors:
  # Login page
  login:
    username: "#username"
    password: "#password"
    submit: "button[type='submit'], #signin-btn"
    error_message: ".login-error, .error-message, .alert-danger"
    success_indicator: ".user-greeting, [data-uname='headerUsername'], .logged-in"
    
  # Search/filter page
  search:
    make_input: "#input-group-make input, [data-uname='makeInput']"
    make_dropdown: "#makes-list, .make-dropdown"
    model_input: "#input-group-model input, [data-uname='modelInput']"
    model_dropdown: "#models-list, .model-dropdown"
    year_from: "#yearFrom, [data-uname='yearFromSelect']"
    year_to: "#yearTo, [data-uname='yearToSelect']"
    odometer_from: "#odometerFrom"
    odometer_to: "#odometerTo"
    search_button: "button[data-uname='searchBtn'], #searchBtn, .search-button"
    clear_filters: "[data-uname='clearFilters'], .clear-filters"
    
  # Results page
  results:
    listing_row: "[data-uname='lotsSearchResultsTable'] tbody tr, .search-results-row, .lot-row"
    listing_card: ".lot-card, [data-lot-id]"
    lot_link: "a[data-uname='lotsSearchLotNumberLink'], a.lot-link"
    lot_number: "[data-uname='lotNumber'], .lot-number"
    vehicle_info: ".vehicle-info, .lot-details"
    current_bid: "[data-uname='currentBid'], .current-bid, .bid-price"
    buy_now: "[data-uname='buyNowPrice'], .buy-now-price"
    odometer: "[data-uname='odometer'], .odometer"
    damage_type: "[data-uname='damageType'], .damage-type"
    location: "[data-uname='location'], .yard-location"
    sale_date: "[data-uname='saleDate'], .sale-date"
    thumbnail: ".lot-image img, [data-uname='lotImage']"
    no_results: ".no-results, .empty-results, [data-uname='noResults']"
    pagination_next: "a[data-uname='nextPageLink']:not(.disabled), .pagination-next:not(.disabled)"
    pagination_info: "[data-uname='paginationInfo'], .pagination-info"
    total_count: "[data-uname='totalResultsCount'], .results-count"
    
  # Detail page
  detail:
    title: "h1, .lot-title"
    lot_number: "[data-uname='lotNumber'], .lot-number-detail"
    vin: "[data-uname='VIN'] span, .vin-value, [data-test='vin']"
    odometer: "[data-uname='odometer'], .odometer-value"
    engine: "[data-uname='engine'], .engine-info"
    transmission: "[data-uname='transmission'], .transmission-info"
    drive_type: "[data-uname='driveType'], .drive-type"
    fuel_type: "[data-uname='fuelType'], .fuel-type"
    color: "[data-uname='color'], .exterior-color"
    interior_color: "[data-uname='interiorColor'], .interior-color"
    keys: "[data-uname='keys'], .keys-info"
    airbags: "[data-uname='airbags'], .airbags-info"
    damage_primary: "[data-uname='primaryDamage'], .primary-damage"
    damage_secondary: "[data-uname='secondaryDamage'], .secondary-damage"
    seller: "[data-uname='seller'], .seller-info"
    title_type: "[data-uname='titleType'], .title-type"
    sale_date: "[data-uname='saleDate'], .auction-date"
    location: "[data-uname='yardLocation'], .yard-info"
    current_bid: "[data-uname='currentBid'], .current-bid-detail"
    buy_now: "[data-uname='buyNow'], .buy-now-detail"
    images: ".gallery-image img, [data-uname='galleryImage'] img, .vehicle-image"
    description: ".lot-description, [data-uname='lotDescription']"
    specs_table: ".vehicle-specs tr, .lot-specs-table tr"

# Timeouts in milliseconds
timeouts:
  navigation: 30000
  element: 10000
  page_load: 60000

# Rate limiting to avoid detection
rate_limit:
  min_delay_ms: 2000
  max_delay_ms: 5000
  
# Retry configuration  
retries:
  max_attempts: 3
  backoff_ms: 1000
```

### /config/settings.py

```python
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

load_dotenv()


def load_site_config(site: str = "copart") -> Dict[str, Any]:
    """Load site-specific configuration from YAML file"""
    config_path = Path(__file__).parent / f"{site}.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_settings() -> Dict[str, str]:
    """Get application settings from environment variables"""
    required_vars = [
        "DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "COPART_USERNAME",
        "COPART_PASSWORD",
    ]
    
    settings = {}
    missing = []
    
    for var in required_vars:
        value = os.environ.get(var)
        if not value:
            missing.append(var)
        settings[var.lower()] = value
    
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")
    
    return settings


def get_optional_setting(key: str, default: str = None) -> str:
    """Get optional setting with default"""
    return os.environ.get(key, default)
```

### /config/__init__.py

```python
from .settings import load_site_config, get_settings, get_optional_setting

__all__ = ["load_site_config", "get_settings", "get_optional_setting"]
```

---

## Step 4: Browser Controller

### /scraper/browser.py

```python
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
```

---

## Step 5: AI Extractor

### /scraper/extractor.py

```python
import json
import re
from typing import List, Optional

import anthropic

from models.schemas import CarListing, CarDetail


class ListingExtractor:
    """
    AI-powered extraction of car listing data from HTML.
    Uses Claude to parse unstructured HTML into structured data.
    """
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
    def _truncate_html(self, html: str, max_chars: int = 50000) -> str:
        """
        Truncate HTML while trying to preserve structure.
        Focuses on keeping the main content area.
        """
        if len(html) <= max_chars:
            return html
            
        # Try to find main content markers
        content_markers = [
            '<table', '<tbody', 'results', 'listings', 'lot-', 'vehicle'
        ]
        
        best_start = 0
        for marker in content_markers:
            idx = html.lower().find(marker)
            if idx > 0 and idx < len(html) // 2:
                best_start = max(0, idx - 1000)
                break
        
        truncated = html[best_start:best_start + max_chars]
        
        # Try to end at a closing tag
        last_close = truncated.rfind(">")
        if last_close > max_chars - 2000:
            truncated = truncated[:last_close + 1]
            
        return truncated + "\n<!-- content truncated -->"
        
    def _clean_json_response(self, response_text: str) -> str:
        """Extract JSON from potentially markdown-wrapped response"""
        text = response_text.strip()
        
        # Remove markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
            
        return text.strip()
        
    async def extract_listings(self, html: str, source_url: str = "") -> List[CarListing]:
        """
        Extract car listings from search results page HTML.
        Returns list of CarListing objects.
        """
        truncated_html = self._truncate_html(html, max_chars=50000)
        
        prompt = f"""Extract all car listings from this auction search results page HTML.

HTML CONTENT:
{truncated_html}

INSTRUCTIONS:
For each car listing visible in the HTML, extract the following fields:
- id: The lot number or unique identifier (REQUIRED - skip listing if not found)
- url: Full URL to the listing detail page (construct from lot number if needed)
- year: Model year as integer
- make: Manufacturer name (Honda, Toyota, Ford, etc.)
- model: Model name (Accord, Camry, F-150, etc.)
- trim: Trim level if shown (EX, LX, Sport, etc.)
- miles: Odometer reading as integer (remove commas)
- current_bid: Current bid amount as integer (remove $ and commas)
- buy_now_price: Buy now price as integer if available
- condition: Vehicle condition (Run and Drive, Enhanced, etc.)
- damage_type: Primary damage type (Front End, Side, Rear, etc.)
- secondary_damage: Secondary damage if listed
- location: Yard or city location
- sale_date: Auction date in ISO format if shown
- thumbnail_url: URL to thumbnail image

OUTPUT FORMAT:
Return ONLY a valid JSON array. No explanations, no markdown formatting.
Use null for any fields that cannot be found.
If no listings are found, return an empty array: []

EXAMPLE OUTPUT:
[
  {{
    "id": "12345678",
    "url": "https://www.copart.com/lot/12345678",
    "year": 2020,
    "make": "Honda",
    "model": "Accord",
    "trim": "Sport",
    "miles": 45000,
    "current_bid": 8500,
    "buy_now_price": null,
    "condition": "Run and Drive",
    "damage_type": "Front End",
    "secondary_damage": null,
    "location": "Nashville, TN",
    "sale_date": "2024-01-15T10:00:00",
    "thumbnail_url": "https://example.com/image.jpg"
  }}
]"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text
            cleaned_json = self._clean_json_response(response_text)
            
            listings_data = json.loads(cleaned_json)
            
            # Convert to Pydantic models
            listings = []
            for item in listings_data:
                try:
                    item["source_site"] = "copart"
                    # Ensure URL is set
                    if not item.get("url") and item.get("id"):
                        item["url"] = f"https://www.copart.com/lot/{item['id']}"
                    listing = CarListing(**item)
                    listings.append(listing)
                except Exception as e:
                    print(f"  Skipping invalid listing: {e}")
                    continue
                    
            return listings
            
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Response was: {response_text[:500]}...")
            return []
        except Exception as e:
            print(f"Extraction error: {e}")
            return []
            
    async def extract_detail(self, html: str, listing_id: str, listing_url: str = "") -> Optional[CarDetail]:
        """
        Extract full vehicle details from a listing detail page.
        Returns CarDetail object or None on failure.
        """
        truncated_html = self._truncate_html(html, max_chars=40000)
        
        prompt = f"""Extract full vehicle details from this auction listing detail page HTML.

HTML CONTENT:
{truncated_html}

INSTRUCTIONS:
Extract all available vehicle information into a single JSON object:

Basic Info:
- id: Lot number (use "{listing_id}" if not found in HTML)
- url: Page URL
- year: Model year
- make: Manufacturer
- model: Model name
- trim: Trim level
- miles: Odometer reading (integer)
- current_bid: Current bid (integer)
- buy_now_price: Buy now price (integer)
- condition: Vehicle condition
- damage_type: Primary damage
- secondary_damage: Secondary damage
- location: Yard location
- sale_date: Auction date (ISO format)

Detail Info:
- vin: 17-character VIN
- engine: Engine description
- transmission: Transmission type (Automatic, Manual, CVT)
- drive_type: Drive type (FWD, RWD, AWD, 4WD)
- fuel_type: Fuel type (Gasoline, Diesel, Electric, Hybrid)
- color: Exterior color
- interior_color: Interior color
- keys: Key status (Yes, No, Unknown)
- airbags: Airbag status
- seller: Seller name or type
- title_type: Title type (Clean, Salvage, Rebuilt, etc.)
- images: Array of full image URLs
- description: Any description text

OUTPUT FORMAT:
Return ONLY a valid JSON object. No explanations, no markdown.
Use null for fields that cannot be found.

EXAMPLE:
{{
  "id": "{listing_id}",
  "year": 2020,
  "make": "Honda",
  "model": "Accord",
  "vin": "1HGCV1F34LA000000",
  "miles": 45000,
  "engine": "1.5L I4 Turbo",
  "transmission": "CVT",
  "color": "Blue",
  "images": ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]
}}"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text
            cleaned_json = self._clean_json_response(response_text)
            
            detail_data = json.loads(cleaned_json)
            
            # Ensure required fields
            detail_data["id"] = detail_data.get("id") or listing_id
            detail_data["source_site"] = "copart"
            detail_data["url"] = detail_data.get("url") or listing_url
            
            return CarDetail(**detail_data)
            
        except json.JSONDecodeError as e:
            print(f"JSON parse error for listing {listing_id}: {e}")
            return None
        except Exception as e:
            print(f"Detail extraction error for {listing_id}: {e}")
            return None
```

---

## Step 6: PostgreSQL Storage

### /scraper/storage.py

```python
from datetime import datetime
from typing import List, Optional

import asyncpg

from models.schemas import CarListing, CarDetail, SearchCriteria


class Storage:
    """
    PostgreSQL storage for car listings and scrape runs.
    Uses a separate 'scraper' schema to avoid conflicts with other tables.
    """
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        
    async def connect(self):
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        print("Connected to database")
        
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            print("Database connection closed")
            
    async def init_schema(self):
        """Create tables if they don't exist"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                -- Create schema
                CREATE SCHEMA IF NOT EXISTS scraper;
                
                -- Listings table (basic info from search results)
                CREATE TABLE IF NOT EXISTS scraper.listings (
                    id VARCHAR(50) NOT NULL,
                    source_site VARCHAR(20) NOT NULL,
                    url TEXT,
                    year INTEGER,
                    make VARCHAR(50),
                    model VARCHAR(100),
                    trim VARCHAR(100),
                    miles INTEGER,
                    current_bid INTEGER,
                    buy_now_price INTEGER,
                    condition VARCHAR(100),
                    damage_type VARCHAR(100),
                    secondary_damage VARCHAR(100),
                    location VARCHAR(200),
                    sale_date TIMESTAMP,
                    thumbnail_url TEXT,
                    scraped_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (source_site, id)
                );
                
                -- Details table (full info from detail pages)
                CREATE TABLE IF NOT EXISTS scraper.details (
                    id VARCHAR(50) NOT NULL,
                    source_site VARCHAR(20) NOT NULL,
                    vin VARCHAR(17),
                    engine VARCHAR(200),
                    transmission VARCHAR(100),
                    drive_type VARCHAR(20),
                    fuel_type VARCHAR(50),
                    color VARCHAR(50),
                    interior_color VARCHAR(50),
                    keys VARCHAR(20),
                    airbags VARCHAR(200),
                    seller VARCHAR(200),
                    title_type VARCHAR(50),
                    images TEXT[],
                    description TEXT,
                    scraped_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (source_site, id),
                    FOREIGN KEY (source_site, id) 
                        REFERENCES scraper.listings(source_site, id)
                        ON DELETE CASCADE
                );
                
                -- Scrape runs tracking
                CREATE TABLE IF NOT EXISTS scraper.runs (
                    id SERIAL PRIMARY KEY,
                    site VARCHAR(20) NOT NULL,
                    criteria JSONB,
                    started_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP,
                    listings_found INTEGER DEFAULT 0,
                    details_fetched INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'running'
                );
                
                -- Indexes for common queries
                CREATE INDEX IF NOT EXISTS idx_listings_make 
                    ON scraper.listings(make);
                CREATE INDEX IF NOT EXISTS idx_listings_model 
                    ON scraper.listings(model);
                CREATE INDEX IF NOT EXISTS idx_listings_make_model 
                    ON scraper.listings(make, model);
                CREATE INDEX IF NOT EXISTS idx_listings_year 
                    ON scraper.listings(year);
                CREATE INDEX IF NOT EXISTS idx_listings_price 
                    ON scraper.listings(current_bid);
                CREATE INDEX IF NOT EXISTS idx_listings_scraped 
                    ON scraper.listings(scraped_at DESC);
                CREATE INDEX IF NOT EXISTS idx_listings_sale_date
                    ON scraper.listings(sale_date);
                CREATE INDEX IF NOT EXISTS idx_details_vin
                    ON scraper.details(vin);
            """)
        print("Database schema initialized")
            
    async def upsert_listing(self, listing: CarListing):
        """Insert or update a single listing"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO scraper.listings 
                    (id, source_site, url, year, make, model, trim, miles,
                     current_bid, buy_now_price, condition, damage_type,
                     secondary_damage, location, sale_date, thumbnail_url,
                     scraped_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $17)
                ON CONFLICT (source_site, id) DO UPDATE SET
                    url = COALESCE(EXCLUDED.url, scraper.listings.url),
                    current_bid = COALESCE(EXCLUDED.current_bid, scraper.listings.current_bid),
                    buy_now_price = COALESCE(EXCLUDED.buy_now_price, scraper.listings.buy_now_price),
                    sale_date = COALESCE(EXCLUDED.sale_date, scraper.listings.sale_date),
                    updated_at = NOW()
            """,
                listing.id,
                listing.source_site,
                listing.url,
                listing.year,
                listing.make,
                listing.model,
                listing.trim,
                listing.miles,
                listing.current_bid,
                listing.buy_now_price,
                listing.condition,
                listing.damage_type,
                listing.secondary_damage,
                listing.location,
                listing.sale_date,
                listing.thumbnail_url,
                datetime.utcnow()
            )
            
    async def upsert_listings(self, listings: List[CarListing]):
        """Insert or update multiple listings"""
        for listing in listings:
            await self.upsert_listing(listing)
            
    async def upsert_detail(self, detail: CarDetail):
        """Insert or update listing detail"""
        # First ensure the listing exists
        await self.upsert_listing(detail)
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO scraper.details
                    (id, source_site, vin, engine, transmission, drive_type,
                     fuel_type, color, interior_color, keys, airbags, seller,
                     title_type, images, description, scraped_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                ON CONFLICT (source_site, id) DO UPDATE SET
                    vin = COALESCE(EXCLUDED.vin, scraper.details.vin),
                    engine = COALESCE(EXCLUDED.engine, scraper.details.engine),
                    transmission = COALESCE(EXCLUDED.transmission, scraper.details.transmission),
                    drive_type = COALESCE(EXCLUDED.drive_type, scraper.details.drive_type),
                    fuel_type = COALESCE(EXCLUDED.fuel_type, scraper.details.fuel_type),
                    color = COALESCE(EXCLUDED.color, scraper.details.color),
                    interior_color = COALESCE(EXCLUDED.interior_color, scraper.details.interior_color),
                    keys = COALESCE(EXCLUDED.keys, scraper.details.keys),
                    airbags = COALESCE(EXCLUDED.airbags, scraper.details.airbags),
                    seller = COALESCE(EXCLUDED.seller, scraper.details.seller),
                    title_type = COALESCE(EXCLUDED.title_type, scraper.details.title_type),
                    images = COALESCE(EXCLUDED.images, scraper.details.images),
                    description = COALESCE(EXCLUDED.description, scraper.details.description),
                    scraped_at = NOW()
            """,
                detail.id,
                detail.source_site,
                detail.vin,
                detail.engine,
                detail.transmission,
                detail.drive_type,
                detail.fuel_type,
                detail.color,
                detail.interior_color,
                detail.keys,
                detail.airbags,
                detail.seller,
                detail.title_type,
                detail.images,
                detail.description,
                datetime.utcnow()
            )
            
    async def get_listings(
        self,
        make: str = None,
        model: str = None,
        year_min: int = None,
        year_max: int = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[CarListing]:
        """Query listings with optional filters"""
        conditions = ["1=1"]
        params = []
        param_idx = 1
        
        if make:
            conditions.append(f"make ILIKE ${param_idx}")
            params.append(f"%{make}%")
            param_idx += 1
        if model:
            conditions.append(f"model ILIKE ${param_idx}")
            params.append(f"%{model}%")
            param_idx += 1
        if year_min:
            conditions.append(f"year >= ${param_idx}")
            params.append(year_min)
            param_idx += 1
        if year_max:
            conditions.append(f"year <= ${param_idx}")
            params.append(year_max)
            param_idx += 1
            
        params.extend([limit, offset])
        
        query = f"""
            SELECT * FROM scraper.listings
            WHERE {' AND '.join(conditions)}
            ORDER BY scraped_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [CarListing(**dict(row)) for row in rows]
            
    async def get_listings_without_details(self, limit: int = 50) -> List[CarListing]:
        """Get listings that don't have detail records yet"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT l.* 
                FROM scraper.listings l
                LEFT JOIN scraper.details d 
                    ON l.id = d.id AND l.source_site = d.source_site
                WHERE d.id IS NULL
                ORDER BY l.scraped_at DESC
                LIMIT $1
            """, limit)
            return [CarListing(**dict(row)) for row in rows]
            
    async def start_run(self, site: str, criteria: SearchCriteria) -> int:
        """Record start of a scrape run, return run ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO scraper.runs (site, criteria, status)
                VALUES ($1, $2, 'running')
                RETURNING id
            """, site, criteria.model_dump_json())
            return row["id"]
            
    async def complete_run(
        self,
        run_id: int,
        listings_found: int,
        details_fetched: int = 0,
        errors: int = 0,
        status: str = "completed"
    ):
        """Record completion of a scrape run"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE scraper.runs
                SET completed_at = NOW(),
                    listings_found = $2,
                    details_fetched = $3,
                    errors = $4,
                    status = $5
                WHERE id = $1
            """, run_id, listings_found, details_fetched, errors, status)
            
    async def get_stats(self) -> dict:
        """Get overall statistics"""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_listings,
                    COUNT(DISTINCT make) as unique_makes,
                    COUNT(DISTINCT (make, model)) as unique_models,
                    MIN(scraped_at) as first_scraped,
                    MAX(scraped_at) as last_scraped
                FROM scraper.listings
            """)
            
            detail_count = await conn.fetchval(
                "SELECT COUNT(*) FROM scraper.details"
            )
            
            return {
                "total_listings": stats["total_listings"],
                "unique_makes": stats["unique_makes"],
                "unique_models": stats["unique_models"],
                "details_fetched": detail_count,
                "first_scraped": stats["first_scraped"],
                "last_scraped": stats["last_scraped"]
            }
```

### /scraper/__init__.py

```python
from .browser import AuctionBrowser
from .extractor import ListingExtractor
from .storage import Storage

__all__ = ["AuctionBrowser", "ListingExtractor", "Storage"]
```

---

## Step 7: Main CLI Entry Point

### main.py

```python
import asyncio
from datetime import datetime

import click
from dotenv import load_dotenv

from config import load_site_config, get_settings
from models.schemas import SearchCriteria
from scraper import AuctionBrowser, ListingExtractor, Storage

load_dotenv()


@click.group()
def cli():
    """Auction Car Scraper - Find and track auction vehicles"""
    pass


@cli.command()
def init_db():
    """Initialize database schema"""
    async def _init():
        settings = get_settings()
        storage = Storage(settings["database_url"])
        await storage.connect()
        await storage.init_schema()
        await storage.close()
        click.echo("✅ Database schema initialized!")
        
    asyncio.run(_init())


@cli.command()
def stats():
    """Show database statistics"""
    async def _stats():
        settings = get_settings()
        storage = Storage(settings["database_url"])
        await storage.connect()
        
        s = await storage.get_stats()
        
        click.echo("\n📊 Database Statistics:")
        click.echo(f"   Total listings: {s['total_listings']:,}")
        click.echo(f"   Unique makes: {s['unique_makes']}")
        click.echo(f"   Unique models: {s['unique_models']}")
        click.echo(f"   Details fetched: {s['details_fetched']:,}")
        if s['first_scraped']:
            click.echo(f"   First scraped: {s['first_scraped']}")
            click.echo(f"   Last scraped: {s['last_scraped']}")
        
        await storage.close()
        
    asyncio.run(_stats())


@cli.command()
@click.option("--make", required=True, help="Car make (e.g., Honda)")
@click.option("--model", default=None, help="Car model (e.g., Accord)")
@click.option("--year-min", type=int, default=None, help="Minimum year")
@click.option("--year-max", type=int, default=None, help="Maximum year")
@click.option("--max-miles", type=int, default=None, help="Maximum mileage")
@click.option("--max-pages", type=int, default=10, help="Max pages to scrape")
@click.option("--headless/--no-headless", default=True, help="Run browser in headless mode")
def search(make, model, year_min, year_max, max_miles, max_pages, headless):
    """Search for cars and save listings to database"""
    criteria = SearchCriteria(
        make=make,
        model=model,
        year_min=year_min,
        year_max=year_max,
        max_miles=max_miles
    )
    asyncio.run(_run_search(criteria, max_pages, headless))


async def _run_search(criteria: SearchCriteria, max_pages: int, headless: bool):
    """Execute the search workflow"""
    settings = get_settings()
    config = load_site_config("copart")
    
    # Initialize components
    browser = AuctionBrowser(config)
    extractor = ListingExtractor(settings["anthropic_api_key"])
    storage = Storage(settings["database_url"])
    
    await storage.connect()
    await browser.start(headless=headless)
    
    run_id = await storage.start_run("copart", criteria)
    total_listings = 0
    errors = 0
    
    try:
        # Try to load saved session
        click.echo("\n🔐 Checking authentication...")
        session_loaded = await browser.load_cookies()
        
        if session_loaded:
            # Verify session is still valid by navigating to search
            await browser.page.goto(config["urls"]["search"])
            if await browser.is_logged_in():
                click.echo("   Using saved session")
            else:
                session_loaded = False
                
        if not session_loaded:
            click.echo("   Logging in...")
            success = await browser.login(
                settings["copart_username"],
                settings["copart_password"]
            )
            if not success:
                raise click.ClickException("❌ Login failed! Check credentials.")
            await browser.save_cookies()
            click.echo("   ✅ Login successful!")
        
        # Perform search
        click.echo(f"\n🔍 Searching for {criteria.make} {criteria.model or '(all models)'}...")
        await browser.search(criteria)
        
        # Process result pages
        page_num = 1
        while page_num <= max_pages:
            click.echo(f"\n📄 Processing page {page_num}...")
            
            try:
                html = await browser.get_page_html()
                listings = await extractor.extract_listings(html, await browser.get_current_url())
                
                if not listings:
                    click.echo("   No listings found on this page")
                    if page_num == 1:
                        click.echo("   (Search may have returned no results)")
                    break
                    
                await storage.upsert_listings(listings)
                total_listings += len(listings)
                click.echo(f"   ✅ Extracted {len(listings)} listings")
                
                # Show sample
                if listings:
                    sample = listings[0]
                    click.echo(f"   Sample: {sample.year} {sample.make} {sample.model} - ${sample.current_bid or 'N/A'}")
                
            except Exception as e:
                click.echo(f"   ❌ Error: {e}")
                errors += 1
                if errors >= 3:
                    click.echo("   Too many errors, stopping")
                    break
            
            # Check for next page
            if not await browser.has_next_page():
                click.echo("\n   No more pages available")
                break
                
            click.echo("   Going to next page...")
            if not await browser.go_next_page():
                break
            page_num += 1
            
        # Complete run
        await storage.complete_run(run_id, total_listings, 0, errors)
        
        click.echo(f"\n{'='*50}")
        click.echo(f"✅ Search complete!")
        click.echo(f"   Listings found: {total_listings}")
        click.echo(f"   Pages processed: {page_num}")
        click.echo(f"   Errors: {errors}")
        click.echo(f"{'='*50}\n")
        
    except Exception as e:
        await storage.complete_run(run_id, total_listings, 0, errors + 1, status="failed")
        click.echo(f"\n❌ Search failed: {e}")
        raise
        
    finally:
        await browser.close()
        await storage.close()


@cli.command()
@click.option("--limit", type=int, default=50, help="Max listings to process")
@click.option("--headless/--no-headless", default=True, help="Run browser in headless mode")
def fetch_details(limit, headless):
    """Fetch full details for listings that don't have them"""
    asyncio.run(_run_fetch_details(limit, headless))


async def _run_fetch_details(limit: int, headless: bool):
    """Fetch details for listings missing them"""
    settings = get_settings()
    config = load_site_config("copart")
    
    browser = AuctionBrowser(config)
    extractor = ListingExtractor(settings["anthropic_api_key"])
    storage = Storage(settings["database_url"])
    
    await storage.connect()
    await browser.start(headless=headless)
    
    try:
        # Get listings needing details
        listings = await storage.get_listings_without_details(limit)
        
        if not listings:
            click.echo("✅ All listings already have details!")
            return
            
        click.echo(f"\n📋 Found {len(listings)} listings needing details")
        
        # Login
        if not await browser.load_cookies():
            click.echo("🔐 Logging in...")
            await browser.login(
                settings["copart_username"],
                settings["copart_password"]
            )
            await browser.save_cookies()
        
        success_count = 0
        error_count = 0
        
        for i, listing in enumerate(listings, 1):
            click.echo(f"\n[{i}/{len(listings)}] Fetching {listing.id}...")
            
            try:
                if not listing.url:
                    listing.url = f"https://www.copart.com/lot/{listing.id}"
                    
                html = await browser.go_to_listing(listing.url)
                detail = await extractor.extract_detail(html, listing.id, listing.url)
                
                if detail:
                    await storage.upsert_detail(detail)
                    click.echo(f"   ✅ {detail.year} {detail.make} {detail.model}")
                    if detail.vin:
                        click.echo(f"      VIN: {detail.vin}")
                    success_count += 1
                else:
                    click.echo(f"   ⚠️ Could not extract details")
                    error_count += 1
                    
            except Exception as e:
                click.echo(f"   ❌ Error: {e}")
                error_count += 1
                continue
                
        click.echo(f"\n{'='*50}")
        click.echo(f"✅ Detail fetch complete!")
        click.echo(f"   Successful: {success_count}")
        click.echo(f"   Errors: {error_count}")
        click.echo(f"{'='*50}\n")
        
    finally:
        await browser.close()
        await storage.close()


@cli.command()
@click.option("--headless/--no-headless", default=False, help="Run in headless mode")
def test_login(headless):
    """Test login functionality"""
    asyncio.run(_test_login(headless))


async def _test_login(headless: bool):
    """Test the login flow"""
    settings = get_settings()
    config = load_site_config("copart")
    
    browser = AuctionBrowser(config)
    await browser.start(headless=headless)
    
    try:
        click.echo("\n🔐 Testing login...")
        success = await browser.login(
            settings["copart_username"],
            settings["copart_password"]
        )
        
        if success:
            click.echo("✅ Login successful!")
            await browser.save_cookies()
            click.echo("   Cookies saved for future use")
        else:
            click.echo("❌ Login failed!")
            await browser.screenshot("login_failure.png")
            click.echo("   Screenshot saved to login_failure.png")
            
    finally:
        await browser.close()


@cli.command()
@click.option("--make", default=None, help="Filter by make")
@click.option("--model", default=None, help="Filter by model")
@click.option("--limit", type=int, default=20, help="Number of results")
def list_cars(make, model, limit):
    """List cars in the database"""
    asyncio.run(_list_cars(make, model, limit))


async def _list_cars(make: str, model: str, limit: int):
    """List cars from database"""
    settings = get_settings()
    storage = Storage(settings["database_url"])
    await storage.connect()
    
    try:
        listings = await storage.get_listings(make=make, model=model, limit=limit)
        
        if not listings:
            click.echo("No cars found matching criteria")
            return
            
        click.echo(f"\n📋 Found {len(listings)} cars:\n")
        
        for car in listings:
            bid_str = f"${car.current_bid:,}" if car.current_bid else "No bid"
            miles_str = f"{car.miles:,} mi" if car.miles else "N/A"
            click.echo(f"  {car.id}: {car.year} {car.make} {car.model} | {miles_str} | {bid_str}")
            if car.damage_type:
                click.echo(f"          Damage: {car.damage_type}")
                
    finally:
        await storage.close()


if __name__ == "__main__":
    cli()
```

---

## Step 8: Render Deployment

### render.yaml

```yaml
services:
  # Background worker for scheduled scraping
  - type: worker
    name: auction-scraper
    runtime: python
    region: oregon
    plan: starter
    buildCommand: |
      pip install -r requirements.txt
      playwright install chromium
      playwright install-deps chromium
    # Default: search for Honda Accords
    startCommand: python main.py search --make Honda --model Accord --max-pages 10
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: your-database-name  # Replace with your actual DB name
          property: connectionString
      - key: ANTHROPIC_API_KEY
        sync: false  # Set in Render dashboard
      - key: COPART_USERNAME
        sync: false  # Set in Render dashboard
      - key: COPART_PASSWORD
        sync: false  # Set in Render dashboard
      - key: PYTHON_VERSION
        value: "3.11"
    autoDeploy: false  # Manual deploys for scraper
```

### README.md

```markdown
# Auction Car Scraper

AI-powered scraper for auction car websites. Extracts vehicle listings and details using Playwright for browser automation and Claude for intelligent data extraction.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

3. Initialize the database:
   ```bash
   python main.py init-db
   ```

## Usage

### Search for cars
```bash
# Search for Honda Accords
python main.py search --make Honda --model Accord

# Search with filters
python main.py search --make Toyota --model Camry --year-min 2018 --max-pages 5

# Run with visible browser (for debugging)
python main.py search --make Honda --no-headless
```

### Fetch full details
```bash
# Fetch details for listings that don't have them
python main.py fetch-details --limit 50
```

### Other commands
```bash
# Test login
python main.py test-login

# View database stats
python main.py stats

# List cars in database
python main.py list-cars --make Honda --limit 20
```

## Deployment

Deploy to Render as a background worker:

1. Connect your GitHub repo to Render
2. Create a new Background Worker
3. Set environment variables in Render dashboard
4. Deploy

## Cost Estimates

- ~$0.01-0.05 per page of search results (AI extraction)
- ~$0.02-0.05 per detail page
- Typical daily run (100 listings): ~$1-3
- Monthly budget of $150 supports heavy usage

## Project Structure

```
/auction-scraper
  /config          # Site configs and settings
  /models          # Pydantic data models
  /scraper         # Browser, extractor, storage
  main.py          # CLI entry point
```
```

---

## Models __init__.py

### /models/__init__.py

```python
from .schemas import SearchCriteria, CarListing, CarDetail, ScrapeRun

__all__ = ["SearchCriteria", "CarListing", "CarDetail", "ScrapeRun"]
```

---

## Final Notes

After Claude Code creates these files:

1. **Test locally first:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   python main.py init-db
   python main.py test-login --no-headless
   python main.py search --make Honda --max-pages 2 --no-headless
   ```

2. **Verify selectors:** The selectors in `copart.yaml` are educated guesses. You may need to inspect the actual site and update them.

3. **Add more sites later:** Copy `copart.yaml` to `iaai.yaml` and update selectors.

4. **Scale up gradually:** Start with small runs, verify data quality, then increase `--max-pages`.

5. **Monitor costs:** Check your Anthropic dashboard after a few runs to verify costs match estimates.
