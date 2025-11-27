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
