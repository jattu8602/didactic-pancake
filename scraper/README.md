# College Contact Scraper

Scrape phone numbers, emails, and websites for any college in India using Google Search + Playwright browser automation.

---

## Requirements

- Python 3.8+
- Chrome/Chromium browser (Playwright installs its own)

## Quick Install

```bash
cd scraper
pip install -r requirements.txt
playwright install chromium
```

## How It Works

For each college in your CSV, the scraper:

1. **Searches Google** using Playwright (real browser) with stealth patches to avoid detection.
2. **Visits the top result** (prefers `.ac.in`, `.gov.in`, `.org` domains).
3. **Extracts phone numbers & emails** from the page body using regex.
4. **Checks /contact, /about, /contact-us** pages if nothing found on homepage.
5. **Saves to** `data/scraped/{district}.csv` with progress tracking.

### Data Flow

```
college CSV → Google Search → Visit Website → Extract Contact Info → Save CSV
                    ↓                                     ↑
              No results?                          Check /contact
              Try URL construction                  /about pages
              (ac.in, .org, .com)                          
```

## Usage

### List districts in a state

```bash
python3 scraper.py --csv ../data/mp_colleges.csv --state "Madhya Pradesh" list
```

### Scrape a specific district

```bash
python3 scraper.py --csv ../data/mp_colleges.csv --state "Madhya Pradesh" "Bhopal"
```

Omit `--state` to search across all states in the CSV:

```bash
python3 scraper.py --csv ../data/all_colleges.csv "Chennai"
```

### Check progress

```bash
python3 scraper.py summary
```

---

## IP Blocking & Proxies

### Why IP Blocking Happens

Google detects automated requests and shows a **captcha or "unusual traffic" page**. This scraper uses:

- **Playwright** (real Chromium browser, not HTTP requests)
- **Stealth JS patches** to hide `navigator.webdriver` and other automation flags
- **Random delays** (5-10s between searches)
- **Desktop user-agent** (Chrome 120)

Despite these, if you scrape too aggressively, Google will block your IP.

### How to Bypass

#### 1. Use a Proxy (Recommended)

Pass proxy to Playwright in `scraper.py`:

```python
context = browser.new_context(
    proxy={"server": "http://your-proxy:port"},
    ...
)
```

Free proxy sources:
- `https://free-proxy-list.net/`
- `https://www.proxynova.com/`

#### 2. Rotate User-Agents

The scraper currently uses one UA. Rotate from a list each request:

```python
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ...",
    "Mozilla/5.0 (X11; Linux x86_64) ...",
]
```

#### 3. Increase Delay

Change at the top of `scraper.py`:

```python
SEARCH_DELAY_S = (10, 20)   # wait 10-20s between searches
```

Higher delays = slower but safer.

#### 4. Use Residential Proxies (Paid)

Services like **BrightData**, **ScrapingBee**, or **Smartproxy** provide residential IPs that are much harder to detect.

---

## Refresh Time Estimation

| District Size | Avg Time | Example |
|--------------|----------|---------|
| 1-10 colleges | 2-5 min | Alirajpur (4) |
| 10-50 colleges | 10-45 min | Umaria (11) |
| 50-100 colleges | 45-90 min | Balaghat (55) |
| 200-350 colleges | 3-6 hrs | Bhopal (343) |

Each college takes **~20-30 seconds** total (search + visit + delay).

---

## How to Modify the Code

### Scrape additional fields

Edit the `visit_and_scrape()` function to save more data:

```python
# After page loads
text = page.inner_text("body")
college_name = page.title()           # page title
address = page.inner_text("address")  # address element
social_links = page.locator('a[href*="facebook"], a[href*="twitter"]').all()

# Add to output
out = {
    **row,
    "website": contact["website"],
    "phone_numbers": "; ".join(contact["phones"]),
    "emails": "; ".join(contact["emails"]),
    "page_title": college_name,
}
```

### Add new search sources

Add a fallback search function in `search_google()` style:

```python
def search_bing(page, query):
    page.goto(f"https://www.bing.com/search?q={quote(query)}")
    # extract results...
```

Then call it if Google fails:

```python
search_results = search_google(page, query)
if not search_results:
    search_results = search_bing(page, query)
```

### Increase phone/email extraction accuracy

Tweak the regex patterns at the top of `scraper.py`:

```python
PHONE_PATTERNS = [
    re.compile(r'\+91[-\s]?[6-9]\d{9}'),          # +91 9876543210
    re.compile(r'0[-\s]?\d{2,4}[-\s]?\d{6,8}'),   # 0755-2554423 (landline)
    re.compile(r'(?<!\d)[6-9]\d{9}(?!\d)'),        # 9876543210
]

# Exclude more unwanted emails
EXCLUDE_EMAILS = re.compile(r'^(noreply|donotreply|no-reply|notifications|nobody|example|test|admin|root|webmaster|info|support|contact|help|facebook|twitter|instagram)@', re.I)
```

---

## Website

The project includes a browse UI:

```bash
# Start the Go server
cd ..
go build -o server . && ./server
# → http://localhost:3000
```

Features:
- Filter by state and district
- Search by college name
- Sortable columns
- Export filtered data as **CSV** or **Excel**
- Paginated table view

---

## Project Structure

```
colleges-api-master/
├── data/
│   ├── mp_colleges.csv           # Source college data
│   └── scraped/                  # Per-district scrape output
│       ├── alirajpur.csv
│       ├── dindori.csv
│       └── ...
├── scraper/
│   ├── scraper.py                # Scraping engine
│   ├── district_progress.json    # Resume tracking
│   ├── requirements.txt          # Python deps
│   └── README.md                 # This file
├── public/
│   ├── browse.html               # Frontend UI
│   ├── data/colleges.json        # Combined data for frontend
│   └── style.css
├── main.go                       # Go server
├── handlers/                     # API handlers
├── config/                       # DB config
└── entities/                     # Data models
```
