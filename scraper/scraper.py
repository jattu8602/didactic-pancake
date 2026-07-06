import csv
import re
import json
import time
import os
import sys
import argparse
import signal
import fcntl
import hashlib
import queue
import threading
import urllib.request
from urllib.parse import urlparse, quote
from random import randint, choice
from collections import Counter

from playwright.sync_api import sync_playwright

OUTPUT_DIR = "../data/scraped"
TRACKER_FILE = "district_progress.json"
BROWSER_HEADLESS = True
SEARCH_DELAY_S = (3, 7)
VISIT_DELAY_S = (1, 3)
WORKERS = 5
PROXY_LIST = []
proxy_lock = threading.Lock()

PHONE_PATTERNS = [
    re.compile(r'\+91[-\s]?[6-9]\d{9}'),
    re.compile(r'0[-\s]?\d{2,4}[-\s]?\d{6,8}'),
    re.compile(r'(?<!\d)[6-9]\d{9}(?!\d)'),
    re.compile(r'\+91\s?\d{10}'),
]

EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
EXCLUDE_EMAILS = re.compile(r'^(noreply|donotreply|no-reply|notifications|nobody|example|test|admin|root|webmaster|info|support|contact|help)@', re.I)

CONTACT_PATHS = ["/contact", "/contact-us", "/contactus", "/contact.html",
                 "/Contact", "/Contact-Us", "/Contacts",
                 "/about", "/about-us", "/about-us.html",
                 "/aboutus", "/About", "/About-Us",
                 "/reach-us", "/get-in-touch",
                 "/enquiry", "/enquiry-form",
                 "/admission", "/admissions"]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:122.0) Gecko/20100101 Firefox/122.0",
]

VIEWPORTS = [
    {"width": 1280, "height": 800},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
]

LOCALES = ["en-IN", "en-US", "en-GB", "en"]

running = True


def handle_signal(signum, frame):
    global running
    print("\n\nCaught signal — finishing current college, then stopping...")
    running = False

LOCK_FILE = TRACKER_FILE + ".lock"
csv_locks = {}

def get_csv_lock(path):
    if path not in csv_locks:
        csv_locks[path] = threading.Lock()
    return csv_locks[path]

def acquire_lock():
    try:
        lf = open(LOCK_FILE, "w")
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lf
    except (IOError, OSError):
        return None

def release_lock(lf):
    if lf:
        try:
            fcntl.flock(lf, fcntl.LOCK_UN)
            lf.close()
        except Exception:
            pass

def load_tracker():
    lf = None
    while lf is None:
        lf = acquire_lock()
        if lf is None:
            time.sleep(0.2)
    try:
        if os.path.exists(TRACKER_FILE):
            with open(TRACKER_FILE) as f:
                return json.load(f)
        return {"districts": {}}
    finally:
        release_lock(lf)

def save_tracker(tracker):
    lf = None
    while lf is None:
        lf = acquire_lock()
        if lf is None:
            time.sleep(0.2)
    try:
        os.makedirs(os.path.dirname(TRACKER_FILE) or ".", exist_ok=True)
        if os.path.exists(TRACKER_FILE):
            existing = json.load(open(TRACKER_FILE))
        else:
            existing = {"districts": {}}
        for d, info in tracker.get("districts", {}).items():
            cur = existing["districts"].get(d, {})
            cur["total"] = info.get("total", cur.get("total", 0))
            cur["completed"] = max(info.get("completed", 0), cur.get("completed", 0))
            existing["districts"][d] = cur
        with open(TRACKER_FILE, "w") as f:
            json.dump(existing, f, indent=2)
    finally:
        release_lock(lf)

def get_next_proxy():
    with proxy_lock:
        if not PROXY_LIST:
            return None
        p = PROXY_LIST.pop(0)
        PROXY_LIST.append(p)
        return p

def parse_proxy_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = re.match(r'((\w+)://)?((\w+):(\w+)@)?([\w.-]+):(\d+)', line)
    if not m:
        return None
    scheme = m.group(2) or "http"
    if m.group(3):
        return {"server": f"{scheme}://{m.group(6)}:{m.group(7)}",
                "username": m.group(4), "password": m.group(5)}
    return {"server": f"{scheme}://{m.group(6)}:{m.group(7)}"}

def load_proxies(path):
    global PROXY_LIST
    PROXY_LIST = []
    with open(path) as f:
        for line in f:
            p = parse_proxy_line(line)
            if p:
                PROXY_LIST.append(p)
    print(f"Loaded {len(PROXY_LIST)} proxies from {path}")

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"

def firecrawl_request(endpoint, data):
    key = FIRECRAWL_API_KEY
    if not key:
        return None
    try:
        req = urllib.request.Request(
            f"{FIRECRAWL_BASE}/{endpoint}",
            data=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read())
        if body.get("success"):
            return body.get("data")
    except Exception as e:
        print(f"    Firecrawl {endpoint} failed: {e}")
    return None

def firecrawl_search(query, limit=5):
    data = firecrawl_request("search", {
        "query": query,
        "searchOptions": {"limit": limit},
    })
    if not data:
        return None
    results = []
    for item in data if isinstance(data, list) else data.get("data", []):
        url = item.get("url", item.get("link", ""))
        title = item.get("title", item.get("name", ""))
        if url:
            results.append({"url": url, "title": title})
    return results if results else None

def firecrawl_scrape(url):
    data = firecrawl_request("scrape", {
        "url": url,
        "pageOptions": {"onlyMainContent": True},
    })
    if not data:
        return None
    text = data.get("markdown", "") or data.get("text", "") or ""
    metadata = data.get("metadata", {}) or {}
    return text, metadata

def get_district_summary():
    tracker = load_tracker()
    for d, info in tracker["districts"].items():
        done = info.get("completed", 0)
        total = info.get("total", 0)
        pct = f"{done/total*100:.0f}%" if total else "0%"
        status = "DONE" if done >= total else ("PARTIAL" if done else "PENDING")
        print(f"  [{status:7}] {done:4d}/{total:<4d} ({pct:>3}) - {d}")
    total_done = sum(v.get("completed", 0) for v in tracker["districts"].values())
    total_all = sum(v.get("total", 0) for v in tracker["districts"].values())
    if total_all:
        print(f"\n  Overall: {total_done}/{total_all} ({total_done/total_all*100:.0f}%)")

def build_search_query(row):
    parts = [row["name"], row["city"], row["district"], row["state"]]
    query = " ".join(p for p in parts if p and p != "NA")
    return f"{query} official website contact"

def extract_phones(text):
    found = set()
    for pat in PHONE_PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group().strip())
    validated = []
    for p in found:
        digits = re.sub(r'\D', '', p)
        if len(digits) >= 10 and len(digits) <= 13:
            validated.append(p)
    return validated

def extract_emails(text):
    return list(set(e for e in EMAIL_PATTERN.findall(text) if not EXCLUDE_EMAILS.match(e)))

def extract_search_results(page, exclude_domains):
    seen = set()
    results = []
    all_links = page.locator('a[href]')
    count = all_links.count()
    for i in range(count):
        try:
            href = all_links.nth(i).get_attribute("href")
            text = all_links.nth(i).inner_text().strip()
            if (href and text and href.startswith("http")
                    and not any(d in href for d in exclude_domains)
                    and href not in seen):
                seen.add(href)
                results.append({"url": re.sub(r'#:~:text=.*', '', href), "title": text})
        except Exception:
            continue
        if len(results) >= 10:
            break
    official = [r for r in results if re.search(r'\.(ac\.in|edu\.in|org|gov\.in)', r['url'])]
    if official:
        return official[:5]
    return results[:5]

def search_google(page, query, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            url = f"https://www.google.co.in/search?q={quote(query)}&hl=en"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)
            try:
                consent = page.locator('button:has-text("Accept all")')
                if consent.count():
                    consent.click()
                    time.sleep(1)
            except Exception:
                pass
            results = extract_search_results(page, ["google.com", "google.co.in"])
            if results:
                return results
        except Exception as e:
            if attempt < max_retries:
                time.sleep((attempt + 1) * 8)
    return []

def search_bing(page, query, max_retries=1):
    for attempt in range(max_retries + 1):
        try:
            url = f"https://www.bing.com/search?q={quote(query)}"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.5)
            results = extract_search_results(page, ["bing.com"])
            if results:
                return results
        except Exception as e:
            if attempt < max_retries:
                time.sleep((attempt + 1) * 8)
    return []

def search_with_fallback(page, query):
    results = search_google(page, query)
    if results:
        return results
    return search_bing(page, query)

def try_construct_url(name):
    slug = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
    words = name.lower().split()
    initials = "".join(w[0] for w in words if w[0].isalpha())
    candidates = []
    for s in set([slug, initials]):
        for tld in [".ac.in", ".org", ".com", ".edu.in", ".co.in", ".in"]:
            candidates.append(f"https://www.{s}{tld}")
            candidates.append(f"https://{s}{tld}")
    return candidates[:15]

def probe_url(url, timeout=6):
    try:
        req = urllib.request.Request(url, method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status < 400
    except Exception:
        return False

def visit_and_scrape(page, url, max_retries=1):
    for attempt in range(max_retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(1)
            text = page.inner_text("body")
            phone_numbers = extract_phones(text)
            emails = extract_emails(text)
            if not phone_numbers and not emails:
                parsed = urlparse(url)
                base = f"{parsed.scheme}://{parsed.netloc}"
                for p in CONTACT_PATHS:
                    try:
                        page.goto(base + p, wait_until="domcontentloaded", timeout=12000)
                        time.sleep(0.5)
                        t2 = page.inner_text("body")
                        phone_numbers = extract_phones(t2)
                        emails = extract_emails(t2)
                        if phone_numbers or emails:
                            break
                    except Exception:
                        continue
            return phone_numbers, emails
        except Exception:
            if attempt < max_retries:
                time.sleep(2)
    return [], []

def save_result(row, contact, output_path):
    district = row["district"].strip()
    safe_name = district.lower().replace(' ', '_')
    output_path = os.path.join(OUTPUT_DIR, f"{safe_name}.csv")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    th_lock = get_csv_lock(output_path)

    with th_lock:
        existing = []
        done_ids = set()
        if os.path.exists(output_path):
            with open(output_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                existing = list(reader)
                done_ids = {r["id"] for r in existing}

        if row["id"] in done_ids:
            return False

        out = {
            **row,
            "website": contact.get("website", ""),
            "phone_numbers": "; ".join(contact.get("phones", [])),
            "emails": "; ".join(contact.get("emails", [])),
        }
        existing.append(out)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(out.keys()))
            writer.writeheader()
            writer.writerows(existing)

        tracker = load_tracker()
        if district not in tracker["districts"]:
            tracker["districts"][district] = {"total": 0, "completed": 0}
        done_with_ids = {r["id"] for r in existing}
        tracker["districts"][district]["completed"] = len(done_with_ids)
        save_tracker(tracker)

    return True

def build_browser(proxy=None):
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=BROWSER_HEADLESS,
        args=["--disable-blink-features=AutomationControlled",
              "--no-sandbox", "--disable-setuid-sandbox",
              "--disable-dev-shm-usage"])
    ctx_kwargs = {
        "user_agent": choice(USER_AGENTS),
        "viewport": choice(VIEWPORTS),
        "locale": choice(LOCALES),
        "color_scheme": "light",
    }
    if proxy:
        ctx_kwargs["proxy"] = proxy
    context = browser.new_context(**ctx_kwargs)
    context.add_init_script(STEALTH_JS)
    page = context.new_page()
    return p, browser, context, page

def firecrawl_process_college(row):
    query = build_search_query(row)
    results = firecrawl_search(query)
    if not results:
        return None

    contact = {"website": "", "phones": [], "emails": []}
    for res in results:
        text, meta = firecrawl_scrape(res["url"]) or ("", {})
        if text:
            phones = extract_phones(text)
            emails = extract_emails(text)
            contact["phones"].extend(phones)
            contact["emails"].extend(emails)
            if not contact["website"]:
                contact["website"] = res["url"]
        if contact["phones"] or contact["emails"]:
            break

    contact["phones"] = list(set(contact["phones"]))
    contact["emails"] = list(set(contact["emails"]))
    return contact


def worker_thread(worker_id, college_queue, total_colleges):
    proxy = get_next_proxy()
    p, browser, context, page = None, None, None, None
    colleges_done = 0

    try:
        p, browser, context, page = build_browser(proxy)

        while running:
            try:
                item = college_queue.get_nowait()
            except queue.Empty:
                break

            row, district_total = item
            wid = f"[W{worker_id}]"

            print(f"\n{wid} {row['name'][:55]}")
            contact = {"website": "", "phones": [], "emails": []}

            try:
                if FIRECRAWL_API_KEY:
                    fc = firecrawl_process_college(row)
                    if fc and (fc["phones"] or fc["emails"] or fc["website"]):
                        contact = fc
                        print(f"{wid} firecrawl ok")

                if not contact["website"] and not contact["phones"]:
                    query = build_search_query(row)
                    search_results = search_with_fallback(page, query)

                    if search_results:
                        contact["website"] = search_results[0]["url"]
                        phones, emails = visit_and_scrape(page, contact["website"])
                        contact["phones"] = phones
                        contact["emails"] = emails

                        if not phones:
                            for sr in search_results[1:4]:
                                p2, e2 = visit_and_scrape(page, sr["url"])
                                contact["phones"].extend(p2)
                                contact["emails"].extend(e2)
                                if contact["phones"]:
                                    break

                    if not contact["website"]:
                        candidates = try_construct_url(row["name"])
                        for cu in candidates:
                            if probe_url(cu):
                                contact["website"] = cu
                                phones, emails = visit_and_scrape(page, cu)
                                contact["phones"] = phones
                                contact["emails"] = emails
                                break

                contact["phones"] = list(set(contact["phones"]))
                contact["emails"] = list(set(contact["emails"]))

                if contact["website"]:
                    print(f"{wid} url: {contact['website'][:70]}")
                if contact["phones"]:
                    print(f"{wid} phones: {contact['phones'][:3]}")
                if contact["emails"]:
                    print(f"{wid} emails: {contact['emails'][:2]}")

            except Exception as e:
                print(f"{wid} error: {e}")

            save_result(row, contact, OUTPUT_DIR)
            colleges_done += 1

            delay = randint(*SEARCH_DELAY_S)
            time.sleep(delay)

    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if p:
            try:
                p.stop()
            except Exception:
                pass

    return colleges_done

def scrape_all(rows, continuous=False, workers=WORKERS):
    global running
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    loop = 1
    while running:
        incomplete_districts = get_incomplete_districts(rows)
        if not incomplete_districts:
            print("\n✅ All districts complete!")
            break

        all_pending = []
        for district, total in incomplete_districts:
            safe_name = district.lower().replace(' ', '_')
            output_path = os.path.join(OUTPUT_DIR, f"{safe_name}.csv")
            done_ids = set()
            if os.path.exists(output_path):
                with open(output_path, newline="", encoding="utf-8") as f:
                    done_ids = {r["id"] for r in csv.DictReader(f)}
            pending = [r for r in rows if r["district"].strip() == district and r["id"] not in done_ids]
            for p in pending:
                all_pending.append((p, total))

        if not all_pending:
            continue

        print(f"\n{'#'*60}")
        print(f"  Loop #{loop} — {len(all_pending)} colleges across {len(incomplete_districts)} districts")
        print(f"  Workers: {workers}")
        print(f"{'#'*60}")

        college_queue = queue.Queue()
        for item in all_pending:
            college_queue.put(item)

        n_workers = min(workers, len(all_pending))
        threads = []
        for i in range(n_workers):
            t = threading.Thread(target=worker_thread, args=(i + 1, college_queue, len(all_pending)))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        if not continuous:
            break
        loop += 1
        if running:
            print("\n  Continuous mode — restarting loop in 30s...")
            time.sleep(30)

    print("\nDone. Final progress:")
    get_district_summary()

def get_incomplete_districts(rows):
    tracker = load_tracker()
    all_dists = Counter(r["district"].strip() for r in rows)
    incomplete = []
    for d, total in all_dists.items():
        info = tracker.get("districts", {}).get(d, {})
        done = info.get("completed", 0)
        if done < total:
            incomplete.append((d, total))
    return sorted(incomplete, key=lambda x: x[1])

def main():
    parser = argparse.ArgumentParser(
        description="College Contact Scraper — Parallel Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scraper.py --csv ../data/mp_colleges.csv list
  python3 scraper.py --csv ../data/mp_colleges.csv --state "Madhya Pradesh" "Bhopal"
  python3 scraper.py --csv ../data/mp_colleges.csv --state "Madhya Pradesh" --all
  python3 scraper.py --csv ../data/mp_colleges.csv --state "Madhya Pradesh" --all --workers 10
  python3 scraper.py --csv ../data/mp_colleges.csv --state "Madhya Pradesh" --all --workers 5 --proxy-file proxies.txt
        """
    )
    parser.add_argument("--csv", default="../data/mp_colleges.csv",
                        help="Path to the college CSV file")
    parser.add_argument("--state", default="",
                        help="State name to filter by")
    parser.add_argument("--all", action="store_true",
                        help="Scrape all incomplete districts automatically")
    parser.add_argument("--continuous", action="store_true",
                        help="Keep retrying in a loop (use with --all)")
    parser.add_argument("--workers", type=int, default=WORKERS,
                        help=f"Number of parallel workers (default: {WORKERS})")
    parser.add_argument("--delay", type=int, default=0,
                        help="Base delay between searches in seconds")
    parser.add_argument("--proxy-file", default="",
                        help="File with proxies (one per line)")
    parser.add_argument("--firecrawl", action="store_true",
                        help="Enable Firecrawl AI search (requires FIRECRAWL_API_KEY env)")
    parser.add_argument("command", nargs="?", default="",
                        help="'list', 'summary', 'retry-missing', or a district name to scrape")
    args = parser.parse_args()

    if args.firecrawl or args.command == "retry-missing":
        global FIRECRAWL_API_KEY
        FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
        if not FIRECRAWL_API_KEY:
            print("⚠ FIRECRAWL_API_KEY not set. Set it via env var or sign up at https://firecrawl.dev")
            sys.exit(1)
        print(f"Firecrawl enabled (key: {FIRECRAWL_API_KEY[:8]}...)")

    if args.delay:
        global SEARCH_DELAY_S
        SEARCH_DELAY_S = (args.delay, args.delay + 4)

    if args.proxy_file:
        load_proxies(args.proxy_file)

    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))
    for r in all_rows:
        r["id"] = r.pop("\ufeffid", r.get("id", ""))

    state_filter = args.state.strip()
    if state_filter:
        rows = [r for r in all_rows if r["state"].strip().lower() == state_filter.lower()]
        if not rows:
            print(f"No colleges found for state '{state_filter}'")
            sys.exit(1)
    else:
        rows = all_rows

    if args.all:
        scrape_all(rows, continuous=args.continuous, workers=args.workers)
        return

    if not args.command:
        parser.print_help()
        sys.exit(1)

    command = args.command.lower()
    if command == "summary":
        print("Progress Tracker:\n")
        get_district_summary()
        return

    if command == "list":
        counts = Counter()
        states = set()
        for r in rows:
            counts[r["district"].strip()] += 1
            states.add(r["state"].strip())
        print(f"State(s): {', '.join(sorted(states))}")
        print(f"{'Count':>5}  District")
        print("-" * 40)
        for d, c in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"{c:5d}  {d}")
        print(f"\nTotal: {len(counts)} districts, {sum(counts.values())} colleges")
        return

    if command == "retry-missing":
        print("Retrying colleges with missing contact data...\n")
        iterations = 0
        while running:
            iterations += 1
            missing = []
            for fname in os.listdir(OUTPUT_DIR):
                if not fname.endswith(".csv"):
                    continue
                fpath = os.path.join(OUTPUT_DIR, fname)
                with open(fpath, newline="", encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        has_phone = bool(r.get("phone_numbers", "").strip())
                        has_email = bool(r.get("emails", "").strip())
                        if not has_phone and not has_email:
                            missing.append(r)
                if len(missing) >= 100:
                    break

            if not missing:
                print(f"\n✅ All {sum(1 for _ in csv.DictReader(open(os.path.join(OUTPUT_DIR, f))))} colleges have contact data!")
                break

            print(f"Iteration #{iterations}: {len(missing)} colleges still missing data")

            college_queue = queue.Queue()
            for r in missing[:50]:
                college_queue.put((r, len(missing)))

            n_workers = min(args.workers, college_queue.qsize())
            threads = []
            for i in range(n_workers):
                t = threading.Thread(target=worker_thread, args=(i + 1, college_queue, len(missing)))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()

            print(f"  Done iteration #{iterations}. Re-checking...\n")
            time.sleep(5)

        print("\nFinal stats:")
        get_district_summary()
        return

    district = args.command.strip()
    valid = {r["district"].strip() for r in rows}
    if district not in valid:
        print(f"District '{district}' not found.")
        sys.exit(1)

    print(f"\nScraping {district} with {args.workers} workers...")
    safe_name = district.lower().replace(' ', '_')
    output_path = os.path.join(OUTPUT_DIR, f"{safe_name}.csv")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    done_ids = set()
    if os.path.exists(output_path):
        with open(output_path, newline="", encoding="utf-8") as f:
            done_ids = {r["id"] for r in csv.DictReader(f)}
    pending = [r for r in rows if r["district"].strip() == district and r["id"] not in done_ids]
    print(f"  Total: {len([r for r in rows if r['district'].strip() == district])}, "
          f"Done: {len(done_ids)}, Pending: {len(pending)}")

    tracker = load_tracker()
    if district not in tracker["districts"]:
        tracker["districts"][district] = {"total": 0, "completed": 0}
    tracker["districts"][district]["total"] = len([r for r in rows if r["district"].strip() == district])
    save_tracker(tracker)

    if not pending:
        print("  Nothing to scrape.")
        return

    college_queue = queue.Queue()
    for p in pending:
        college_queue.put((p, len(pending)))

    n_workers = min(args.workers, len(pending))
    threads = []
    for i in range(n_workers):
        t = threading.Thread(target=worker_thread, args=(i + 1, college_queue, len(pending)))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    print(f"\nDone! Results in {output_path}")
    get_district_summary()

if __name__ == "__main__":
    main()
