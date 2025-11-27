#!/usr/bin/env python3
"""
Auction Scraper CLI
Main entry point for the car auction scraper.
"""
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

from config.settings import get_settings, load_site_config
from models.schemas import SearchCriteria
from scraper import AuctionBrowser, ListingExtractor, Storage


# Load environment variables
load_dotenv()


@click.group()
def cli():
    """Auction site scraper - Extract car listings from auction sites."""
    pass


@cli.command()
def init_db():
    """Initialize database schema."""

    async def _init():
        settings = get_settings()
        storage = Storage(settings["database_url"])

        try:
            await storage.connect()
            await storage.init_schema()
            print("\n✓ Database initialized successfully")
        finally:
            await storage.close()

    asyncio.run(_init())


@cli.command()
def stats():
    """Show database statistics."""

    async def _stats():
        settings = get_settings()
        storage = Storage(settings["database_url"])

        try:
            await storage.connect()
            data = await storage.get_stats()

            print("\n" + "="*60)
            print("DATABASE STATISTICS")
            print("="*60)
            print(f"Total Listings:      {data['total_listings']:,}")
            print(f"Unique VINs:         {data['unique_vins']:,}")
            print(f"Unique Makes:        {data['unique_makes']:,}")
            print(f"Unique Models:       {data['unique_models']:,}")
            print(f"Details Fetched:     {data['details_fetched']:,}")

            if data['first_scraped']:
                print(f"First Scraped:       {data['first_scraped']}")
            if data['last_scraped']:
                print(f"Last Scraped:        {data['last_scraped']}")
            print("="*60 + "\n")

        finally:
            await storage.close()

    asyncio.run(_stats())


@cli.command()
@click.option('--make', required=True, help='Vehicle make (e.g., Honda, Toyota)')
@click.option('--model', help='Vehicle model (e.g., Accord, Camry)')
@click.option('--year-min', type=int, help='Minimum year')
@click.option('--year-max', type=int, help='Maximum year')
@click.option('--max-miles', type=int, help='Maximum mileage')
@click.option('--max-price', type=int, help='Maximum current bid')
@click.option('--max-pages', type=int, default=5, help='Maximum pages to scrape')
@click.option('--headless/--no-headless', default=True, help='Run browser in headless mode')
@click.option('--site', default='copart', help='Auction site to scrape')
def search(make: str, model: Optional[str], year_min: Optional[int],
           year_max: Optional[int], max_miles: Optional[int],
           max_price: Optional[int], max_pages: int, headless: bool, site: str):
    """Search for cars and save listings to database."""

    async def _search():
        # Load settings and config
        settings = get_settings()
        config = load_site_config(site)

        # Create search criteria
        criteria = SearchCriteria(
            make=make,
            model=model,
            year_min=year_min,
            year_max=year_max,
            max_miles=max_miles,
            max_price=max_price
        )

        # Initialize components
        browser = AuctionBrowser(config)
        extractor = ListingExtractor(settings["anthropic_api_key"])
        storage = Storage(settings["database_url"])

        try:
            # Connect to database
            await storage.connect()

            # Start scrape run tracking
            run_id = await storage.start_run(site, criteria)
            print(f"\nStarted scrape run #{run_id}")
            print(f"Criteria: {make} {model or 'All Models'}")
            if year_min or year_max:
                print(f"Years: {year_min or 'Any'} - {year_max or 'Any'}")

            # Start browser
            print("\nLaunching browser...")
            await browser.start(headless=headless)

            # Login
            print("\nLogging in...")
            login_success = await browser.login(
                settings["copart_username"],
                settings["copart_password"]
            )

            if not login_success:
                print("❌ Login failed!")
                await storage.complete_run(run_id, 0, 0, 1, "failed")
                return

            # Save cookies for future use
            await browser.save_cookies()

            # Perform search
            print("\nPerforming search...")
            search_success = await browser.search(criteria)

            if not search_success:
                print("❌ Search failed!")
                await storage.complete_run(run_id, 0, 0, 1, "failed")
                return

            # Scrape pages
            total_listings = 0
            errors = 0
            page = 1

            while page <= max_pages:
                print(f"\n{'='*60}")
                print(f"PAGE {page}/{max_pages}")
                print(f"{'='*60}")

                # Get page HTML
                html = await browser.get_page_html()

                # Extract listings
                print("Extracting listings with AI...")
                listings = await extractor.extract_listings(html)

                if not listings:
                    print("No listings found on this page")
                    break

                print(f"Found {len(listings)} listings")

                # Save to database
                print("Saving to database...")
                try:
                    await storage.upsert_listings(listings)
                    total_listings += len(listings)
                    print(f"✓ Saved {len(listings)} listings")
                except Exception as e:
                    print(f"❌ Database error: {e}")
                    errors += 1

                # Check for next page
                if page < max_pages:
                    if await browser.has_next_page():
                        print("\nGoing to next page...")
                        if not await browser.go_next_page():
                            print("Failed to navigate to next page")
                            break
                        page += 1
                    else:
                        print("\nNo more pages available")
                        break
                else:
                    page += 1

            # Complete run
            await storage.complete_run(
                run_id,
                total_listings,
                0,  # details fetched separately
                errors,
                "completed"
            )

            print(f"\n{'='*60}")
            print(f"SCRAPE COMPLETE")
            print(f"{'='*60}")
            print(f"Run ID:              #{run_id}")
            print(f"Total Listings:      {total_listings}")
            print(f"Pages Scraped:       {page - 1}")
            print(f"Errors:              {errors}")
            print(f"{'='*60}\n")

        except KeyboardInterrupt:
            print("\n\n⚠ Interrupted by user")
            await storage.complete_run(run_id, total_listings, 0, errors, "interrupted")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            await storage.complete_run(run_id, total_listings, 0, errors + 1, "failed")
            raise
        finally:
            await browser.close()
            await storage.close()

    asyncio.run(_search())


@cli.command()
@click.option('--limit', type=int, default=50, help='Max number of details to fetch')
@click.option('--headless/--no-headless', default=True, help='Run browser in headless mode')
@click.option('--site', default='copart', help='Auction site')
def fetch_details(limit: int, headless: bool, site: str):
    """Fetch full details for listings that don't have them yet."""

    async def _fetch_details():
        # Load settings and config
        settings = get_settings()
        config = load_site_config(site)

        # Initialize components
        browser = AuctionBrowser(config)
        extractor = ListingExtractor(settings["anthropic_api_key"])
        storage = Storage(settings["database_url"])

        try:
            # Connect to database
            await storage.connect()

            # Get listings without details
            print(f"\nFinding listings without details (limit: {limit})...")
            listings = await storage.get_listings_without_details(limit)

            if not listings:
                print("✓ All listings already have details!")
                return

            print(f"Found {len(listings)} listings to process")

            # Start browser
            print("\nLaunching browser...")
            await browser.start(headless=headless)

            # Try to load saved cookies
            if await browser.load_cookies():
                print("Using saved session")
            else:
                # Need to login
                print("\nLogging in...")
                login_success = await browser.login(
                    settings["copart_username"],
                    settings["copart_password"]
                )

                if not login_success:
                    print("❌ Login failed!")
                    return

                await browser.save_cookies()

            # Fetch details for each listing
            fetched = 0
            errors = 0

            for i, listing in enumerate(listings, 1):
                print(f"\n[{i}/{len(listings)}] {listing.year} {listing.make} {listing.model} (ID: {listing.id})")

                try:
                    # Navigate to detail page
                    if not listing.url:
                        print("  ⚠ No URL, skipping")
                        continue

                    print(f"  Fetching {listing.url}")
                    html = await browser.go_to_listing(listing.url)

                    # Extract details
                    print("  Extracting details with AI...")
                    detail = await extractor.extract_detail(html, listing.id, listing.url)

                    if detail:
                        # Save to database
                        await storage.upsert_detail(detail)
                        fetched += 1

                        if detail.vin:
                            print(f"  ✓ Saved (VIN: {detail.vin})")
                        else:
                            print(f"  ✓ Saved (no VIN found)")
                    else:
                        print(f"  ❌ Failed to extract details")
                        errors += 1

                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    errors += 1

            print(f"\n{'='*60}")
            print(f"DETAIL FETCH COMPLETE")
            print(f"{'='*60}")
            print(f"Processed:           {len(listings)}")
            print(f"Successfully Fetched: {fetched}")
            print(f"Errors:              {errors}")
            print(f"{'='*60}\n")

        except KeyboardInterrupt:
            print("\n\n⚠ Interrupted by user")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            raise
        finally:
            await browser.close()
            await storage.close()

    asyncio.run(_fetch_details())


@cli.command()
@click.option('--headless/--no-headless', default=False, help='Run browser in headless mode')
@click.option('--site', default='copart', help='Auction site')
def test_login(headless: bool, site: str):
    """Test login to auction site."""

    async def _test_login():
        settings = get_settings()
        config = load_site_config(site)

        browser = AuctionBrowser(config)

        try:
            print("\nLaunching browser...")
            await browser.start(headless=headless)

            print(f"\nTesting login to {site}...")
            print(f"Username: {settings['copart_username']}")

            success = await browser.login(
                settings["copart_username"],
                settings["copart_password"]
            )

            if success:
                print("\n✓ Login successful!")

                # Save cookies
                await browser.save_cookies()
                print("✓ Session cookies saved")

                # Take screenshot
                screenshot_path = f"{site}_logged_in.png"
                await browser.screenshot(screenshot_path)

                if not headless:
                    print("\nBrowser will stay open for 30 seconds...")
                    await asyncio.sleep(30)
            else:
                print("\n❌ Login failed!")

                # Take screenshot for debugging
                screenshot_path = f"{site}_login_failed.png"
                await browser.screenshot(screenshot_path)

        finally:
            await browser.close()

    asyncio.run(_test_login())


@cli.command()
@click.option('--make', help='Filter by make')
@click.option('--model', help='Filter by model')
@click.option('--year-min', type=int, help='Minimum year')
@click.option('--year-max', type=int, help='Maximum year')
@click.option('--limit', type=int, default=20, help='Number of results to show')
@click.option('--offset', type=int, default=0, help='Results offset')
def list_cars(make: Optional[str], model: Optional[str],
              year_min: Optional[int], year_max: Optional[int],
              limit: int, offset: int):
    """List cars from database with optional filters."""

    async def _list_cars():
        settings = get_settings()
        storage = Storage(settings["database_url"])

        try:
            await storage.connect()

            # Query listings
            listings = await storage.get_listings(
                make=make,
                model=model,
                year_min=year_min,
                year_max=year_max,
                limit=limit,
                offset=offset
            )

            if not listings:
                print("\nNo listings found matching criteria")
                return

            # Display results
            print(f"\n{'='*80}")
            print(f"LISTINGS (showing {len(listings)} of {offset + len(listings)}+)")
            print(f"{'='*80}")

            for listing in listings:
                # Header
                title = f"{listing.year or '????'} {listing.make or 'Unknown'} {listing.model or 'Unknown'}"
                if listing.trim:
                    title += f" {listing.trim}"
                print(f"\n{title}")
                print(f"ID: {listing.id} | Source: {listing.source_site}")

                if listing.vin:
                    print(f"VIN: {listing.vin}")

                # Details
                details = []
                if listing.miles is not None:
                    details.append(f"{listing.miles:,} miles")
                if listing.condition:
                    details.append(listing.condition)
                if listing.damage_type:
                    details.append(f"Damage: {listing.damage_type}")
                if details:
                    print(" | ".join(details))

                # Pricing
                pricing = []
                if listing.current_bid is not None:
                    pricing.append(f"Bid: ${listing.current_bid:,}")
                if listing.buy_now_price is not None:
                    pricing.append(f"Buy Now: ${listing.buy_now_price:,}")
                if pricing:
                    print(" | ".join(pricing))

                # Location and date
                info = []
                if listing.location:
                    info.append(listing.location)
                if listing.sale_date:
                    info.append(f"Sale: {listing.sale_date.strftime('%Y-%m-%d %H:%M')}")
                if info:
                    print(" | ".join(info))

                # URL
                if listing.url:
                    print(f"URL: {listing.url}")

                print(f"Scraped: {listing.scraped_at.strftime('%Y-%m-%d %H:%M')}")
                print("-" * 80)

            print()

        finally:
            await storage.close()

    asyncio.run(_list_cars())


if __name__ == "__main__":
    cli()
