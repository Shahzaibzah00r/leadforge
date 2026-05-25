# Leadforge

A stealthy, MX-verifying lead scraper configurable for any country or niche.

<p align="center">
  <strong>Production-grade business lead scraper with stealth, MX verification & global reach</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#installation">Installation</a> •
  <a href="#usage">Usage</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#output">Output</a> •
  <a href="#architecture">Architecture</a>
</p>

---

## Features

| Feature | Description |
|---------|-------------|
| **Stealth Mode** | Auto-rotating User-Agents, realistic browser headers, and randomized delays (2-5s) to avoid bot detection |
| **MX Verification** | Free DNS MX record validation for every extracted email using `dnspython` — no paid APIs needed |
| **Smart Fallbacks** | If a homepage fails or yields no emails, automatically crawls `/contact`, `/about`, `/privacy` |
| **Global Coverage** | Works for any US state or any country worldwide via configurable geography |
| **False-Positive Filter** | Strips image filenames (`.png`, `.jpg`, `.svg`), logos, and placeholder emails |
| **Dual Discovery** | Chamber directories (US) + Bing/Startpage search engines (global) |
| **Rich Data Export** | CSV + JSON + Markdown report with improved WhatsApp verification, deduplication, and quality scoring |
| **Resume Support** | Auto-saves progress to `progress.json` — interrupt and resume anytime |

---

## Installation

### Prerequisites

- Python >= 3.10
- [Playwright](https://playwright.dev/python/) (for search-engine scraping)

### Quick Install

```bash
https://github.com/Shahzaibzah00r/leadforge.git
cd leadforge

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install package + dependencies
pip install -e "."

# Install Playwright browser binaries
python -m playwright install chromium
```

### Development Setup

```bash
# Install dev dependencies (linting, testing, type checking)
pip install -e ".[dev]"

# Or use uv (recommended)
uv sync --dev
```

---

## Usage

### Basic: Default run

```bash
python -m leadforge
```

### Target Another US State

```bash
python -m leadforge \
  --state "Texas" \
  --state-abbr "TX" \
  --cities "Houston,Dallas,Austin,San Antonio"
```

### Target Any Country

```bash
# Pakistan
python -m leadforge \
  --country "Pakistan" \
  --cities "Karachi,Lahore,Islamabad,Rawalpindi"

# United Kingdom
python -m leadforge \
  --country "United Kingdom" \
  --cities "London,Manchester,Birmingham"

# Canada
python -m leadforge \
  --state "Ontario" \
  --country "Canada" \
  --cities "Toronto,Ottawa,Mississauga"
```

### Single Niche Focus

```bash
python -m leadforge --niche "Law firms"
python -m leadforge --niche "Dentists"
python -m leadforge --niche "Real estate agencies"
```

### Environment Variables

Instead of CLI flags, you can export variables:

```bash
export SCRAPER_STATE="Florida"
export SCRAPER_STATE_ABBR="FL"
export SCRAPER_COUNTRY="USA"
export SCRAPER_CITIES="Miami,Orlando,Tampa,Jacksonville"
export MAX_CANDIDATES="500"

python -m leadforge
```

### Resume an Interrupted Run

Progress is auto-saved to `output/progress.json`. Simply re-run:

```bash
python -m leadforge
```

To force a fresh start:

```bash
rm -f output/progress.json && python -m leadforge
```

---

## Configuration

All defaults live in `src/leadforge/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `REQUEST_DELAY_MIN` | `2.0` | Minimum seconds between requests |
| `REQUEST_DELAY_MAX` | `5.0` | Maximum seconds between requests |
| `FETCH_TIMEOUT` | `10` | HTTP request timeout in seconds |
| `MAX_QUERIES` | `100` | Max search-engine queries per run |
| `MAX_CANDIDATES` | `2000` | Stop after accepting this many leads |
| `MIN_RESULTS_PER_QUERY` | `3` | Minimum URLs to consider a query successful |
| `SEARCH_ENGINE_FAILURE_THRESHOLD` | `10` | Abort SE discovery after N consecutive failures |

### Adding Cities

C```python

# src/leadforge/config.py

CITIES = [
    "Phoenix",
    "Scottsdale",
    "Mesa",
    "Your City Here",  # <-- add more
]

```

### Adding Niches

```python
NICHE_MAP = {
    "Dentists": ["dentist", "dental office", "orthodontist"],
    "Law firms": ["law firm", "lawyer", "attorney"],
    "Your Niche": ["keyword1", "keyword2"],  # <-- add here
}

# Also add broad match keywords
NICHE_KEYWORDS = [
    "dent", "dental",
    "law", "attorney",
    "keyword1", "keyword2",  # <-- add here too
]
```

### Adding Chamber Directories (US Only)

If you find a GrowthZone/ChamberMaster directory:

```python
CHAMBER_DIRECTORIES = [
    "https://business.phoenixchamber.com",
    "https://business.yourchamber.com",  # <-- new
]
```

---

## Output

All files are written to the `output/` directory:

### `leads.csv`

Your primary export. Key columns include:

| Column | Description |
|--------|-------------|
| `target_url` | The URL where the lead was found |
| `email` | Extracted and MX-verified email address |
| `domain` | Domain portion of the email |
| `mx_status` | `valid` if MX records exist, `invalid` otherwise |
| `business_name` | Company name from page title or schema |
| `owner_name` | Extracted owner/founder name |
| `phone` | Normalized phone number |
| `whatsapp` | `yes` / `no` (validated via phone number parsing and `api.whatsapp.com` checks) |
| `city` | Parsed city |
| `state` | Parsed state |
| `full_address` | Full street address |
| `website` | Business website URL |
| `niche` | Detected business category |
| `source_type` | `bing`, `startpage`, or chamber name |
| `source_url` | Original discovery URL |
| `notes` | Discovery metadata |

### `leads.json`

Same data as JSON for programmatic consumption.

### `run_report.md`

Human-readable summary including:

- Total candidates discovered
- Accepted vs rejected counts
- Duplicates removed
- Leads by niche
- Leads by city
- Data quality metrics (email coverage, phone coverage, MX validity)
- Top sources

### `rejected_candidates.csv`

Candidates that failed enrichment (insufficient data, unreachable site, etc.) with rejection reasons.

### `progress.json`

Internal resume state. Do not edit manually.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Discovery     │────▶│   Enrichment     │────▶│    Export       │
│                 │     │                  │     │                 │
│ • Chambers (US) │     │ • Rotate UA      │     │ • Deduplicate   │
│ • Bing          │     │ • Random delays  │     │ • WhatsApp check│
│ • Startpage     │     │ • Crawl pages    │     │ • MX verify     │
└─────────────────┘     │ • Extract data   │     │ • CSV/JSON/MD   │
                        │ • Fallback paths │     └─────────────────┘
                        │ • MX validation  │
                        └──────────────────┘
```

### Module Overview

| Module | Responsibility |
|--------|---------------|
| `cli.py` | Entry point, argument parsing, orchestration |
| `config.py` | Constants, geography, niches, thresholds |
| `sources.py` | Chamber scraper + search engine result parsers |
| `enrichment.py` | Website visitor: crawls pages, builds lead records |
| `extractors.py` | HTML/text parsers for emails, phones, addresses, schema.org |
| `browser.py` | Playwright stealth wrapper for search engines |
| `utils.py` | HTTP fetch with stealth, MX verification, normalization |
| `export.py` | Deduplication, WhatsApp checking, file writing |

---

## How It Works

### 1. Discovery Phase

- **Chambers** (US only): Scrapes A-Z member listings from configured chamber directories. Matches business names against niche keywords.
- **Search Engines**: Runs geo-targeted queries like `"Phoenix dentist"` or `"law firm in Pakistan"` via Bing and Startpage. Extracts result URLs and filters out social media / directory blocklist domains.

### 2. Enrichment Phase

- Visits each candidate URL with a **fresh rotated User-Agent** and realistic headers.
- Waits a **random 2-5 seconds** between requests.
- Attempts the homepage first. If it fails or yields no emails, **automatically falls back** to `/contact`, `/about`, `/privacy`.
- Extracts:
  - Emails via regex + false-positive filtering
  - Phones via pattern matching
  - Addresses via city/state regex
  - Owner names via title patterns
  - Schema.org JSON-LD structured data
- **Verifies every email domain** against DNS MX records. No MX = discarded.
- Accepts leads with at least 2 populated core fields (name, website, phone, email, address).

### 3. Export Phase

- Deduplicates by domain, email, and phone.
- Performs a lightweight WhatsApp check via `wa.me`.
- Writes `leads.csv`, `leads.json`, and `run_report.md`.

---

## Development

### Lint & Type Check

```bash
make check
```

### Format Code

```bash
make format
```

### Run Tests

```bash
make test
```

### Available Make Targets

| Command | Description |
|---------|-------------|
| `make install-dev` | Install package + dev dependencies |
| `make check` | Run ruff (lint) and mypy (type check) |
| `make format` | Auto-fix lint issues and format |
| `make test` | Run pytest suite |
| `make clean` | Delete output, caches, build artifacts |

---

## Important Notes

- **Chamber directories hide emails.** They use "Contact Us" forms. Emails only come from the business's own website or schema.org markup.
- **No paid APIs required.** MX verification uses free DNS lookups. Search engines use free Bing/Startpage scraping.
- **Be respectful.** The default delays (2-5s) and 10s timeout are designed to be gentle on target servers. Do not reduce delays below 1s.
- **WhatsApp checks are best-effort.** They use a HEAD request to `wa.me` and may be blocked or rate-limited.

---

## Author

**Shahzaib** — [shahzaibzahoor7@gmail.com](mailto:shahzaibzahoor7@gmail.com)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with stealth, precision, and zero paid APIs.
</p>
