# Auction Scraper

AI-powered web scraper for car auction sites using Playwright and Claude. Extracts vehicle listings from Copart and other auction sites, storing structured data in PostgreSQL.

## Overview

This project combines browser automation with AI to scrape car auction listings:

- **Playwright** for headless browser automation with anti-detection measures
- **Claude (Anthropic)** for intelligent HTML parsing and data extraction
- **PostgreSQL** for structured data storage with VIN-based indexing
- **Click CLI** for easy command-line usage

The scraper navigates auction sites, handles login and search, extracts listings using AI, and stores them in a shared database with the whip-proto project.

## Features

- Automated browser navigation with Playwright
- AI-powered HTML extraction using Claude Sonnet 4
- VIN-based vehicle tracking across auction sites
- PostgreSQL storage with separate 'scraper' schema
- Rate limiting and anti-detection measures
- Session management with cookie persistence
- Configurable search criteria
- Detailed vehicle information extraction
- CLI commands for all operations

## Architecture

```
manheim-scraper/
├── config/
│   ├── copart.yaml      # Site-specific selectors and URLs
│   ├── settings.py      # Environment variable management
│   └── __init__.py
├── models/
│   ├── schemas.py       # Pydantic data models
│   └── __init__.py
├── scraper/
│   ├── browser.py       # Playwright browser controller
│   ├── extractor.py     # Claude-powered HTML extraction
│   ├── storage.py       # PostgreSQL async storage
│   └── __init__.py
├── main.py              # CLI entry point
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (local)
├── .env.example         # Template for environment setup
└── render.yaml          # Render deployment config
```

## Installation

### 1. Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 2. Configure Environment

Copy the example environment file and add your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# Database (shared with whip-proto project)
DATABASE_URL=postgresql://user@localhost/wholesale

# Anthropic API for AI extraction
ANTHROPIC_API_KEY=sk-ant-api03-...

# Copart credentials
COPART_USERNAME=your_username
COPART_PASSWORD=your_password
```

### 3. Initialize Database

Create the database schema (uses separate 'scraper' schema):

```bash
python main.py init-db
```

## Usage

### Test Login

Before scraping, test your credentials:

```bash
# Test with visible browser (no-headless)
python main.py test-login --no-headless

# Test headless (default)
python main.py test-login
```

This saves session cookies to `cookies.json` and takes a screenshot.

### Search for Cars

Search for vehicles and save listings:

```bash
# Basic search - Honda Accord
python main.py search --make Honda --model Accord

# Search with filters
python main.py search \
  --make Toyota \
  --model Camry \
  --year-min 2018 \
  --year-max 2023 \
  --max-pages 10

# Search all Toyota (no model filter)
python main.py search --make Toyota --max-pages 20

# Run with visible browser for debugging
python main.py search --make Honda --no-headless
```

**Options:**
- `--make`: Vehicle make (required)
- `--model`: Vehicle model (optional)
- `--year-min`: Minimum year (optional)
- `--year-max`: Maximum year (optional)
- `--max-miles`: Maximum mileage (optional)
- `--max-price`: Maximum current bid (optional)
- `--max-pages`: Maximum pages to scrape (default: 5)
- `--headless/--no-headless`: Browser visibility (default: headless)
- `--site`: Auction site (default: copart)

### Fetch Details

Get full vehicle details for listings that don't have them yet:

```bash
# Fetch details for up to 50 listings
python main.py fetch-details

# Fetch more listings
python main.py fetch-details --limit 100

# Run with visible browser
python main.py fetch-details --limit 20 --no-headless
```

This command:
1. Finds listings that have no detailed information
2. Navigates to each listing's detail page
3. Extracts full vehicle info with Claude
4. Saves to database (VIN required for details table)

### List Saved Cars

Query and display saved listings:

```bash
# List recent listings
python main.py list-cars

# Filter by make
python main.py list-cars --make Honda

# Filter by make and model
python main.py list-cars --make Honda --model Accord

# Filter by year range
python main.py list-cars --make Toyota --year-min 2020 --year-max 2023

# Show more results
python main.py list-cars --limit 50 --offset 0
```

### Database Statistics

View overall database stats:

```bash
python main.py stats
```

Shows:
- Total listings
- Unique VINs
- Unique makes/models
- Details fetched
- Date range

## Data Models

### CarListing

Basic listing from search results:

```python
{
  "id": "12345678",
  "source_site": "copart",
  "vin": "1HGCV1F34LA000000",
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
  "thumbnail_url": "https://...",
  "scraped_at": "2024-01-10T12:00:00"
}
```

### CarDetail

Full vehicle details (extends CarListing):

```python
{
  # All CarListing fields plus:
  "vin": "1HGCV1F34LA000000",
  "engine": "1.5L I4 Turbo",
  "transmission": "CVT",
  "drive_type": "FWD",
  "fuel_type": "Gasoline",
  "color": "Blue",
  "interior_color": "Black",
  "keys": "Yes",
  "airbags": "Deployed",
  "seller": "Insurance",
  "title_type": "Salvage",
  "images": ["https://...", "https://..."],
  "description": "..."
}
```

## Database Schema

The scraper uses a separate `scraper` schema with three tables:

### scraper.listings
- Primary key: `(source_site, id)`
- Indexed on: `vin`, `make`, `model`, `year`, `price`, `scraped_at`, `sale_date`
- Stores basic listing info from search results

### scraper.details
- Primary key: `vin` (VIN is unique across all auction sites)
- Stores full vehicle details from detail pages
- Only populated when VIN is available

### scraper.runs
- Tracks scrape run metadata
- Records criteria, results, and errors

## Cost Estimates

### Claude API Costs

Using Claude Sonnet 4 (current pricing):
- **Search results extraction**: ~$0.01-0.02 per page (100-200 listings)
- **Detail page extraction**: ~$0.003-0.01 per vehicle

Example costs:
- Scraping 5 pages of search results: ~$0.05-0.10
- Fetching details for 100 vehicles: ~$0.30-1.00

HTML is truncated to 50,000 characters to minimize costs while preserving content.

### Rate Limiting

- Random delays: 2-5 seconds between requests
- Configurable via `config/copart.yaml`
- Prevents detection and bans

## Deployment (Render)

The project includes `render.yaml` for easy deployment:

```bash
# Push to GitHub
git add .
git commit -m "Auction scraper setup"
git push

# Connect repo to Render
# Add environment variables in Render dashboard
# Deploy will run automatically
```

Includes cron jobs for:
- Daily Honda search (2 AM)
- Daily details fetch (4 AM)

## Development

### Project Structure

- **config/**: Site-specific configs and settings
- **models/**: Pydantic data models with validation
- **scraper/**: Core scraping components
  - `browser.py`: Playwright automation
  - `extractor.py`: Claude-powered extraction
  - `storage.py`: PostgreSQL operations
- **main.py**: CLI interface

### Adding New Auction Sites

1. Create `config/[site].yaml` with selectors
2. Update `main.py` to support new site
3. Modify extraction prompts if needed

### VIN as Primary Key

The architecture uses VIN as the universal identifier:
- Vehicles can appear on multiple auction sites
- VIN uniquely identifies each physical vehicle
- Details table uses VIN as primary key
- Listings table has VIN column with index

## Troubleshooting

### Login Issues

```bash
# Test with visible browser to debug
python main.py test-login --no-headless

# Check screenshot: copart_login_failed.png
# Verify credentials in .env
```

### Extraction Errors

- Check Claude API key in `.env`
- Verify HTML is being fetched (screenshots can help)
- Review truncation settings in `extractor.py`

### Database Errors

```bash
# Re-initialize schema
python main.py init-db

# Check connection
psql $DATABASE_URL

# Verify scraper schema exists
\dn
```

## License

MIT

## Notes

- Uses shared PostgreSQL database with whip-proto project
- VIN-based architecture allows cross-site vehicle tracking
- AI extraction adapts to HTML structure changes
- Session cookies persist between runs
- All scraping respects rate limits and anti-detection measures
