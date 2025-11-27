# Manheim Scraper

Automated web scraping tool for Manheim auction data using Playwright for browser automation.

## Overview

This project uses Playwright to automate data collection from Manheim auction listings and stores the results in a PostgreSQL database (shared with the whip-proto project).

## Features

- Browser automation using Playwright
- PostgreSQL database integration
- Shared database with whip-proto project
- Configurable scraping targets

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install
```

2. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Set the DATABASE_URL environment variable to point to your PostgreSQL database

## Database

This project shares the same PostgreSQL database as the whip-proto project. The database configuration is managed through `db_config.py`.

## Usage

TBD - Scraping scripts and automation workflows to be added

## License

MIT
