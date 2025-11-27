from datetime import datetime
from typing import List, Optional

import asyncpg

from models.schemas import CarListing, CarDetail, SearchCriteria


class Storage:
    """
    PostgreSQL storage for car listings and scrape runs.
    Uses a separate 'scraper' schema to avoid conflicts with other tables.
    VIN is the primary key for vehicles across all auction sites.
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
                -- VIN is the primary key since it's unique across all sites
                CREATE TABLE IF NOT EXISTS scraper.listings (
                    vin VARCHAR(17),
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
                    vin VARCHAR(17) PRIMARY KEY,
                    id VARCHAR(50),
                    source_site VARCHAR(20),
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
                    scraped_at TIMESTAMP DEFAULT NOW()
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
                CREATE INDEX IF NOT EXISTS idx_listings_vin
                    ON scraper.listings(vin);
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
            """)
        print("Database schema initialized")

    async def upsert_listing(self, listing: CarListing):
        """Insert or update a single listing"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO scraper.listings
                    (id, source_site, vin, url, year, make, model, trim, miles,
                     current_bid, buy_now_price, condition, damage_type,
                     secondary_damage, location, sale_date, thumbnail_url,
                     scraped_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $18)
                ON CONFLICT (source_site, id) DO UPDATE SET
                    vin = COALESCE(EXCLUDED.vin, scraper.listings.vin),
                    url = COALESCE(EXCLUDED.url, scraper.listings.url),
                    current_bid = COALESCE(EXCLUDED.current_bid, scraper.listings.current_bid),
                    buy_now_price = COALESCE(EXCLUDED.buy_now_price, scraper.listings.buy_now_price),
                    sale_date = COALESCE(EXCLUDED.sale_date, scraper.listings.sale_date),
                    updated_at = NOW()
            """,
                listing.id,
                listing.source_site,
                listing.vin,
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

        # Only insert details if we have a VIN
        if not detail.vin:
            print(f"  Skipping detail for {detail.id} - no VIN")
            return

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO scraper.details
                    (vin, id, source_site, engine, transmission, drive_type,
                     fuel_type, color, interior_color, keys, airbags, seller,
                     title_type, images, description, scraped_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                ON CONFLICT (vin) DO UPDATE SET
                    id = COALESCE(EXCLUDED.id, scraper.details.id),
                    source_site = COALESCE(EXCLUDED.source_site, scraper.details.source_site),
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
                detail.vin,
                detail.id,
                detail.source_site,
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
        """Get listings that have VIN but don't have detail records yet"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT l.*
                FROM scraper.listings l
                LEFT JOIN scraper.details d ON l.vin = d.vin
                WHERE l.vin IS NOT NULL AND d.vin IS NULL
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
                    COUNT(DISTINCT vin) as unique_vins,
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
                "unique_vins": stats["unique_vins"],
                "unique_makes": stats["unique_makes"],
                "unique_models": stats["unique_models"],
                "details_fetched": detail_count,
                "first_scraped": stats["first_scraped"],
                "last_scraped": stats["last_scraped"]
            }
