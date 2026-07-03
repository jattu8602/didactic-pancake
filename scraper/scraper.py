import csv
import re
import json
import time
import os
import sys
import argparse
from urllib.parse import urlparse, quote
from random import randint

from playwright.sync_api import sync_playwright

OUTPUT_DIR = "../data/scraped"
TRACKER_FILE = "district_progress.json"
BROWSER_HEADLESS = True
SEARCH_DELAY_S = (5, 10)
VISIT_DELAY_S = (2, 4)

PHONE_PATTERNS = [
    re.compile(r'\+91[-\s]?[6-9]\d{9}'),
    re.compile(r'0[-\s]?\d{2,4}[-\s]?\d{6,8}'),
    re.compile(r'(?<!\d)[6-9]\d{9}(?!\d)'),
]

EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

EXCLUDE_EMAILS = re.compile(r'^(noreply|donotreply|no-reply|notifications|nobody|example|test|admin|root|webmaster|info|support|contact|help)@', re.I)

CONTACT_PATHS = ["/contact", "/contact-us", "/contactus", "/about", "/about-us",
                 "/Contact", "/Contact-Us", "/CONTACT", "/About", "/about-us.html"]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
"""


def load_tracker():
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE) as f:
            return json.load(f)
    return {"districts": {}}


def save_tracker(tracker):
    os.makedirs(os.path.dirname(TRACKER_FILE) or ".", exist_ok=True)
    with open(TRACKER_FILE, "w") as f:
        json.dump(tracker, f, indent=2)


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
    return f"{query} official website"


def extract_phones(text):
    found = set()
    for pat in PHONE_PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group().strip())
    return list(found)


def extract_emails(text):
    return list(set(e for e in EMAIL_PATTERN.findall(text) if not EXCLUDE_EMAILS.match(e)))


def search_google(page, query, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            url = f"https://www.google.com/search?q={quote(query)}&hl=en"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            try:
                consent = page.locator('button:has-text("Accept all")')
                if consent.count():
                    consent.click()
                    time.sleep(1)
            except Exception:
                pass

            seen = set()
            results = []
            all_links = page.locator('a[href]')
            count = all_links.count()
            for i in range(count):
                try:
                    href = all_links.nth(i).get_attribute("href")
                    text = all_links.nth(i).inner_text().strip()
                    if (href and text and href.startswith("http")
                            and "google.com" not in href
                            and href not in seen):
                        seen.add(href)
                        results.append({"url": href, "title": text})
                except Exception:
                    continue
                if len(results) >= 8:
                    break

            # Strip Google text fragments from URLs
            for r in results:
                r['url'] = re.sub(r'#:~:text=.*', '', r['url'])

            # Prefer official domains (.ac.in, .org, .edu.in) over directories
            official = [r for r in results if re.search(r'\.(ac\.in|edu\.in|org|gov\.in)', r['url'])]
            if official:
                return official[:5]
            return results[:5]

        except Exception as e:
            if attempt < max_retries:
                wait = (attempt + 1) * 10
                print(f"    search failed, retrying in {wait}s: {e}")
                time.sleep(wait)
            else:
                print(f"    search failed after {max_retries} retries: {e}")
                return []


def try_construct_url(name):
    slug = re.sub(r'[^a-zA-Z0-9]', '', name).lower()
    slug = re.sub(r'\s+', '', slug)
    words = name.lower().split()
    initials = "".join(w[0] for w in words if w[0].isalpha())
    candidates = []
    for s in set([slug, initials]):
        for tld in [".ac.in", ".org", ".com", ".edu.in", ".co.in", ".in"]:
            candidates.append(f"https://www.{s}{tld}")
            candidates.append(f"https://{s}{tld}")
    return candidates[:12]


def probe_url(url, timeout=8):
    import urllib.request
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
                        page.goto(base + p, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(0.5)
                        text2 = page.inner_text("body")
                        phone_numbers = extract_phones(text2)
                        emails = extract_emails(text2)
                        if phone_numbers or emails:
                            break
                    except Exception:
                        continue

            return phone_numbers, emails
        except Exception:
            if attempt < max_retries:
                time.sleep(2)
            else:
                return [], []


def scrape_district(district, all_rows):
    tracker = load_tracker()
    if district not in tracker["districts"]:
        tracker["districts"][district] = {"total": 0, "completed": 0}

    rows = [r for r in all_rows if r["district"].strip() == district]
    tracker["districts"][district]["total"] = len(rows)
    save_tracker(tracker)

    output_path = os.path.join(OUTPUT_DIR, f"{district.lower().replace(' ', '_')}.csv")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if os.path.exists(output_path):
        with open(output_path, newline="", encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
        done_ids = {r["id"] for r in existing}
    else:
        existing = []
        done_ids = set()

    pending = [r for r in rows if r["id"] not in done_ids]
    print(f"  District: {district}")
    print(f"  Total: {len(rows)}, Already done: {len(existing)}, Pending: {len(pending)}")

    if not pending:
        print("  Nothing to scrape.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=BROWSER_HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )
        context.add_init_script(STEALTH_JS)
        page = context.new_page()

        new_results = []
        for idx, row in enumerate(pending, 1):
            name = row["name"]
            city = row.get("city", "")
            print(f"\n  [{idx}/{len(pending)}] {name[:60]}")

            contact = {"website": "", "phones": [], "emails": []}

            # Try Google search first
            query = build_search_query(row)
            search_results = search_google(page, query)

            if search_results:
                contact["website"] = search_results[0]["url"]
                print(f"    website: {contact['website']}")
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

                contact["phones"] = list(set(contact["phones"]))
                contact["emails"] = list(set(contact["emails"]))

            # Fallback: try to construct URL if search gave no website
            if not contact["website"]:
                print("    no search results, trying URL construction...")
                candidates = try_construct_url(name)
                found = False
                for cu in candidates:
                    if probe_url(cu):
                        print(f"    found via construction: {cu}")
                        contact["website"] = cu
                        phones, emails = visit_and_scrape(page, cu)
                        contact["phones"] = phones
                        contact["emails"] = emails
                        contact["phones"] = list(set(contact["phones"]))
                        contact["emails"] = list(set(contact["emails"]))
                        found = True
                        break
                if not found:
                    print("    no URL found")

            out = {
                **row,
                "website": contact["website"],
                "phone_numbers": "; ".join(contact["phones"]),
                "emails": "; ".join(contact["emails"]),
            }
            new_results.append(out)

            done_ids.add(row["id"])
            tracker["districts"][district]["completed"] = len(done_ids)
            save_tracker(tracker)

            all_done = existing + new_results
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(all_done[0].keys()))
                writer.writeheader()
                writer.writerows(all_done)

            delay = randint(*SEARCH_DELAY_S)
            print(f"    delay {delay}s")
            time.sleep(delay)

        browser.close()


def main():
    parser = argparse.ArgumentParser(
        description="Scrape college contact info (phone, email, website) from any state CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scraper.py --csv ../data/mp_colleges.csv list
  python3 scraper.py --csv ../data/colleges.csv --state "Madhya Pradesh" "Bhopal"
  python3 scraper.py --csv ../data/colleges.csv --state "Tamil Nadu" "Chennai"
  python3 scraper.py --csv ../data/colleges.csv summary
        """
    )
    parser.add_argument("--csv", default="../data/mp_colleges.csv",
                        help="Path to the college CSV file (default: ../data/mp_colleges.csv)")
    parser.add_argument("--state", default="",
                        help="State name to filter by (default: all states)")
    parser.add_argument("command", nargs="?", default="",
                        help="'list', 'summary', or a district name to scrape")
    args = parser.parse_args()

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

    if not args.command:
        parser.print_help()
        sys.exit(1)

    command = args.command.lower()

    if command == "summary":
        print("Progress Tracker:\n")
        get_district_summary()
        return

    if command == "list":
        from collections import Counter
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

    district = args.command.strip()
    valid = {r["district"].strip() for r in rows}

    if district not in valid:
        print(f"District '{district}' not found.")
        if state_filter:
            print(f"Use `python3 scraper.py --csv \"{args.csv}\" --state \"{state_filter}\" list` to see available districts.")
        else:
            print(f"Use `python3 scraper.py --csv \"{args.csv}\" list` to see available districts.")
        sys.exit(1)

    scrape_district(district, rows)

    print(f"\nDone! Check {OUTPUT_DIR}/{district.lower().replace(' ', '_')}.csv")
    print("\n--- Updated Progress ---")
    get_district_summary()


if __name__ == "__main__":
    main()
