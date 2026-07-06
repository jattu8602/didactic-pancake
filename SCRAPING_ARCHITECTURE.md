# Scraping Architecture & Operations Manual

## Overview

This project scrapes contact information (emails, phones, professor names) from Indian college/university websites and merges it into a unified `colleges.json` data file. It supports parallel scraping via Docker containers with real-time monitoring through opencode (AI agent).

**Data flow:**
```
College Website → Scraper (Playwright) → scraper_output/*.json → merge_results.py → public/data/colleges.json → Go Server (port 3000)
```

---

## 1. How We Scrape Each College

### 1.1 Generic Playwright Scraper (`scraper/scrape_generic.py`)

The generic scraper uses **Playwright** (headless Chromium) to crawl a college website and extract:

- **Emails** — from `mailto:` links, page text, and obfuscated patterns (`[at]`, `(at)`, etc.)
- **Phones** — Indian mobile numbers (`+91xxxxx`), filtered against ISBNs (978/979 prefix)
- **Professor names** — by examining text near email addresses

**Algorithm:**
1. Load homepage → extract all internal links
2. Prioritize links containing `faculty`, `profile`, `staff`, `people`, `teacher`, etc.
3. Visit up to 40 pages, crawling deeper into profile/faculty sections
4. On each page, extract emails/mailto links and search backward for nearby names
5. Save results to `scraper_output/{college_name}.json`

**Key decisions in `scrape_generic.py`:**
- `MAX_PAGES = 40` — limits crawl depth to avoid infinite loops
- `PROFILE_KEYWORDS` — links matching these are visited first (they have people data)
- `PAGE_KEYWORDS` — secondary priority links (department pages, contact pages)
- Noise filters: emails ending in `.png/.jpg` are rejected; `noreply@`, `webmaster@`, etc. are excluded

### 1.2 Custom Scrapers

Some colleges have unique site structures requiring custom scrapers:

| Scraper | College | Why Custom |
|---------|---------|------------|
| `scrape_dtu.py` | DTU | Faculty data is in per-department `faculty_v2` pages with `mailto:` links |
| `scrape_jnu.py` | JNU | Emails obfuscated as `name[at]domain[dot]ac[dot]in` in Drupal Views |
| `scrape_nsut.py` | NSUT | JS-rendered department pages; profiles at `/en/node/{id}` with `[at]` obfuscation |
| `scrape_sbu.py` | SBU | Full-site crawl with `(at)` obfuscation pattern |
| `scrape_sau.py` | SAU | `(at)` obfuscation, no personal phones listed |

**Example — JNU (`scrape_jnu.py`):**
```python
# JNU uses Drupal Views to render faculty search
# Emails are in <li> elements with [at] and [dot] obfuscation:
#   kavitaarora[at]mail[dot]jnu[dot]ac[dot]in
# Strategy: fetch faculty-search page, parse <li> entries, decode emails

entries = re.findall(r'<li>(.*?)</li>', page_text, re.DOTALL)
for entry in entries:
    if '[at]' not in entry:
        continue
    name = extract_name(entry)
    raw_emails = re.findall(r'([\w.+-]+\[at\][\w.-]+(?:\[dot\]\w+)+)', entry)
    email = raw_email.replace('[at]', '@').replace('[dot]', '.')
```

**Example — DTU (`scrape_dtu.py`):**
```python
# DTU has per-department faculty pages
# Faculty emails are in mailto: links with real emails
# Strategy: iterate 24 departments, fetch each faculty_v2 page

for dept in departments:
    url = f'https://dtu.ac.in/Web/Departments/{dept}/faculty_v2'
    r = requests.get(url, timeout=(5, 10))
    mailtos = re.findall(r'mailto:([\w.+-]+@[\w.-]+\.[a-z]{2,})', r.text)
```

**Example — NSUT (`scrape_nsut.py`):**
```python
# NSUT requires JavaScript rendering for its Drupal views
# Strategy: Playwright to render, extract from table rows

await page.goto(f'https://www.nsut.ac.in/en/department/faculty/{dept_id}')
profs = await page.evaluate('''() => {
    const rows = document.querySelectorAll("table.views-table tbody tr");
    return Array.from(rows).map(row => ({
        name: row.querySelector(".views-field-field-name").innerText.trim(),
        url: "https://www.nsut.ac.in" + row.querySelector(".views-field-view-node a").getAttribute("href")
    }));
}''')
# Then visit each profile page, decode [at] -> @
decoded = re.findall(r'[\w.+-]+(?:\[at\])[\w.-]+(?:\[dot\]\w+)+', profile_text)
email = decoded[0].replace('[at]', '@').replace('[dot]', '.')
```

---

## 2. How We Merge Scraped Data into `colleges.json`

### The Merge Script (`scraper/merge_results.py`)

The merge pipeline:

```
scraper_output/*.json  ──→  merge_results.py  ──→  public/data/colleges.json
```

**Step-by-step:**

1. **Load existing data** — reads `public/data/colleges.json` (3,765 colleges across 34 states)
2. **Map filenames to colleges** — each scraper output file maps to an existing or new college:

```python
UNI_MAP = {
    'dtu':    ('Delhi Technological University', 'Delhi'),
    'jnu':    ('Jawaharlal Nehru University', 'Delhi'),
    'nsut':   ('Netaji Subhas University of Technology', 'Delhi'),
    'iiit_delhi': ('IIIT Delhi', 'Delhi'),
}
```

3. **Clean professor names** — filters out:
   - Role-based text ("Head of Department", "Dean", "Professor")
   - Navigation/menu items ("Home", "Contact", "Search")
   - Truncated names (tabs, too short/long)
   - Non-name patterns ("Since Apr", "Room No")

4. **Match to existing entry** — tries to match by name + state. If no match, creates a new entry
5. **Update or create** — sets `professors` array, updates `emails` and `phone_numbers` fields
6. **Deduplicate** — removes duplicate entries by email across professors

**Output format in `colleges.json`:**
```json
{
  "colleges": [
    {
      "id": "123",
      "state": "Delhi",
      "name": "Jawaharlal Nehru University",
      "website": "http://www.jnu.ac.in/",
      "phone_numbers": "+91-11-26717576",
      "emails": "vc@jnu.ac.in; registrar@jnu.ac.in",
      "professors": [
        {
          "name": "Prof. Kavita Arora",
          "email": "kavitaarora@jnu.ac.in",
          "phone": ""
        }
      ]
    }
  ]
}
```

**Running the merge:**
```bash
python3 scraper/merge_results.py
```

---

## 3. Using Docker for Parallel College Scraping

### 3.1 The Docker Image (`scraper/Dockerfile`)

The image packages Playwright + Chromium + the generic scraper:

```dockerfile
FROM python:3.11-slim
RUN apt-get install -y chromium dependencies
RUN pip install playwright && python3 -m playwright install chromium
COPY scrape_generic.py .
VOLUME /output
ENTRYPOINT ["python3", "scrape_generic.py"]
```

### 3.2 Launching Containers (`scraper/run_six.sh`)

The orchestration script launches 6 containers simultaneously, one per college:

```bash
COLLEGES=(
  "IGDTUW:http://www.igdtuw.ac.in/"
  "IIIT_Delhi:https://www.iiitd.ac.in/"
  "JNU:http://www.jnu.ac.in/"
  "DTU:http://www.dtu.ac.in/"
  "NSUT:https://www.nsut.ac.in/"
  "Jamia_Millia_Islamia:http://www.jmi.ac.in/"
)

for entry in "${COLLEGES[@]}"; do
  NAME="${entry%%:*}"
  URL="${entry#*:}"
  docker run -d \
    --name "scraper_$NAME" \
    -v "$(pwd)/scraper_output:/output" \
    college-scraper \
    --name "$NAME" --url "$URL" --output /output
done
```

**Key aspects:**
- **`-d`** — detached mode, containers run in background
- **`-v`** — bind-mounts a shared host directory so all output lands in one place
- **Container naming** — `scraper_IIIT_Delhi`, `scraper_JNU` etc. for easy reference
- **Shared output volume** — all containers write to `scraper_output/` on the host

**Running manually for a single college:**
```bash
docker run -d \
  --name scraper_IIITD \
  -v "$(pwd)/scraper_output:/output" \
  college-scraper \
  --name "IIIT_Delhi" --url "https://www.iiitd.ac.in/" --output /output
```

### 3.3 Output Structure

Each container writes its results to a JSON file in the shared volume:

```
scraper_output/
├── iiit_delhi.json      # 416 professors, 657 emails
├── dtu.json             # 174 professors, 174 emails
├── jnu.json             # 657 professors, 1,251 emails
├── igdtuw.json          # 19 professors, 55 emails
├── jamia_millia_islamia.json  # 13 professors, 20 emails
└── nsut.json            # (to be scraped)
```

Each JSON file has a consistent schema:
```json
{
  "url": "https://college.edu/",
  "professors": [
    {"name": "Dr. Name", "email": "name@college.edu", "phone": ""}
  ],
  "all_emails": ["...", "..."],
  "all_phones": ["..."],
  "statistics": { "total_professors": 416, ... }
}
```

---

## 4. How opencode Monitors Docker Containers

### 4.1 The Monitoring Loop (`run_six.sh` lines 55-107)

After launching all containers, the script enters an infinite monitoring loop:

```bash
while true; do
  clear
  echo "COLLEGE SCRAPER MONITOR  ($(date +%H:%M:%S))"
  
  ALL_DONE=true
  for c in "${CONTAINERS[@]}"; do
    STATUS=$(docker inspect "$c" --format='{{.State.Status}}')
    LOGS=$(docker logs "$c" --tail 6 2>&1 | tail -5)
    
    echo "── $c [$STATUS] ───"
    echo "$LOGS"
  done
  
  [ "$ALL_DONE" = true ] && break
  sleep 5
done
```

**What it monitors every 5 seconds:**
- **Container status** — `running`, `exited`, `not found`
- **Last 5 log lines** — shows current progress (pages scraped, emails found)
- **Exit codes** — when finished, shows success/failure per container

**Sample monitor output:**
```
── scraper_IIIT_Delhi [running] ──────────────────
  [12/40] /people/faculty -> e:23 p:0
  [13/40] /people/faculty?page=1 -> e:18 p:0

── scraper_JNU [running] ─────────────────────────
  [5/40] /faculty-search -> e:0 p:0 (no structured data)
  ERROR: Connection reset by peer

── scraper_NSUT [exited] ─────────────────────────
  (no logs - check container)
```

### 4.2 opencode's Real-Time Role

As an AI agent, opencode performs additional monitoring beyond the shell script:

1. **`docker logs scraper_IIIT_Delhi --tail 5`** — fetches latest progress on demand
2. **`docker inspect scraper_JNU --format='{{.State.Status}}'`** — checks if container is still alive
3. **Interprets log output** — recognizes when a scraper is stuck (e.g., repeated "ERROR" messages), hitting rate limits, or collecting zero data
4. **Decides on corrective action** — e.g., if DTU times out on HTTPS, switches to HTTP; if JNU returns no structured data, investigates alternative URL patterns
5. **Kills or restarts containers** — `docker rm -f scraper_DTU; docker run ...` with different parameters
6. **Discovers new scraping strategies mid-session** — e.g., finding JNU's obfuscated `[at]` emails requires the agent to inspect raw HTML and write a new regex on the fly

**This is the "boss-employee" pattern:**
- **opencode (boss):** decides WHICH colleges to scrape, WHAT strategy to use, analyzes results, adjusts approach
- **Containers (employees):** execute the scraping task independently, silently producing JSON output
- **The boss supervises multiple employees** running in parallel, checks their progress, and intervenes when an employee fails

---

## 5. Boss-Employee Architecture: AI Agent as Orchestrator

### The Pattern

```
┌─────────────────────────────────────────────────────┐
│                   opencode (Boss)                    │
│                                                      │
│  1. Plans strategy (which colleges, what approach)   │
│  2. Launches containers (hires employees)            │
│  3. Monitors progress (checks in on workers)         │
│  4. Analyzes output (reviews completed work)         │
│  5. Decides next steps (course-corrects)             │
│  6. Merges results (integrates all contributions)    │
└─────────────────────────────────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Container: scraper_IIIT │ Container: scraper_JNU  │ Container: scraper_DTU  │
│ (Employee 1)     │ (Employee 2)     │ (Employee 3)     │
│                   │                   │                   │
│ Crawls iiitd.ac.in │ Crawls jnu.ac.in  │ Crawls dtu.ac.in  │
│ Extracts professors│ Parses Drupal     │ Finds faculty_v2  │
│ Writes to /output  │ Writes to /output │ Writes to /output │
└─────────────────┘ └─────────────────┘ └─────────────────┘
          │                │                │
          └────────────────┼────────────────┘
                           ▼
               ┌─────────────────────┐
               │  scraper_output/    │
               │  (shared filesystem)│
               └─────────────────────┘
                           │
                           ▼
               ┌─────────────────────┐
               │  merge_results.py   │
               │  (Boss consolidates) │
               └─────────────────────┘
                           │
                           ▼
               ┌─────────────────────┐
               │  colleges.json      │
               │  (Final deliverable)│
               └─────────────────────┘
```

### Concrete Example: The Delhi College Scrape Session

| Step | opencode (Boss) Action | Container (Employee) Action |
|------|------------------------|---------------------------|
| 1 | **Plans:** "Scrape 6 Delhi colleges. Use generic Playwright scraper." | — |
| 2 | **Launches:** `docker run -d scraper_IIIT --name IIIT_Delhi --url https://iiitd.ac.in/` | Starts crawling IIITD homepage |
| 3 | **Monitors:** `docker logs scraper_IIIT --tail 3` → "25 pages, 400+ professors" | Reports progress via stdout |
| 4 | **Intervenes:** DTU container stuck (timeout). Checks URL → `dtu.ac.in` needs HTTP, not HTTPS | DTU silently waiting for socket |
| 5 | **Restarts:** Kills DTU container, relaunches with HTTP URL | DTU starts fresh, finds `faculty_v2` pages |
| 6 | **Investigates:** JNU output is empty. Inspects JNU website raw HTML, discovers `[at]` obfuscation | JNU done (0 results with generic approach) |
| 7 | **Writes custom code:** Creates `scrape_jnu.py` with `[at]` → `@` decoder | — |
| 8 | **Launches specialist:** `python3 scraper/scrape_jnu.py` | Custom script runs, extracts 657 professors |
| 9 | **Reviews output:** IIITD (416), DTU (174), JNU (657), IGDTUW (19), Jamia (13) | All employees finished |
| 10 | **Merges:** `python3 scraper/merge_results.py` → 1,350 professors in colleges.json | — |

### Key Boss Responsibilities

1. **Strategy selection:** Decides which URL pattern to use, whether generic or custom scraper is needed
2. **Resource allocation:** Launches up to 6 containers in parallel for concurrency
3. **Error handling:** Detects failures (timeout, empty results, SSL errors) and adjusts approach
4. **Quality control:** Reviews output quality — filters noise, deduplicates, validates emails
5. **Integration:** Runs the merge script to consolidate all results into a single data file
6. **Documentation:** Updates this manual with new patterns discovered during scraping

---

## 6. Scraping Strategies by Site Type

| Site Type | Characteristics | Strategy | Example |
|-----------|----------------|----------|---------|
| **Standard** | Static HTML, clear faculty page | Generic Playwright scraper | IIIT Delhi |
| **Drupal Views** | JS-rendered tables, `[at]` emails | Playwright + DOM evaluation + regex decode | JNU |
| **Department-based** | Per-department faculty pages | Iterate departments, extract mailto: links | DTU |
| **JS-heavy SPA** | React/Angular with API calls | Wireshark/DevTools to find API endpoints | (not yet encountered) |
| **Obfuscated emails** | `name(at)domain(dot)com` | Regex decode: replace `(at)`→`@`, `(dot)`→`.` | SAU, SBU |
| **No structured data** | PDFs, images, no faculty lists | Fallback to Bing search (Firecrawl) | Some MP colleges |

---

## 7. Running the Full Pipeline

```bash
# 1. Build the Docker image
docker build -t college-scraper scraper/

# 2. Launch parallel containers
bash scraper/run_six.sh

# 3. (Alternative) Launch a single container manually
docker run -d --name scraper_JNU \
  -v "$(pwd)/scraper_output:/output" \
  college-scraper --name "JNU" --url "http://www.jnu.ac.in/" --output /output

# 4. Monitor with opencode
docker logs scraper_JNU --tail 5

# 5. Run custom scraper (when generic fails)
python3 scraper/scrape_jnu.py

# 6. Merged all results
python3 scraper/merge_results.py

# 7. Start the server
go run main.go
# → http://localhost:3000 → browse.html
```
