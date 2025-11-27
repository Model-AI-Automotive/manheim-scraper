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
