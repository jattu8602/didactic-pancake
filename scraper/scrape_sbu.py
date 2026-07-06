"""
Scrape https://sbu.ac.in/ — all pages, all professors, phones, emails.
"""
import re, json, sys, time
from urllib.parse import urljoin
from collections import Counter
from playwright.sync_api import sync_playwright

START_URL = "https://sbu.ac.in/"
visited = set()
results = []
PAGE_LIMIT = 200

PHONE_PAT = re.compile(r'\+?\d{2,3}[-.\s]?\d{3,4}[-.\s]?\d{4,8}')
EMAIL_PAT = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PROF_PAT = re.compile(
    r'(Dr\.?|Prof\.?|Mr\.?|Ms\.?|Mrs\.?|Er\.?|Shri\.?|Smt\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',
)

SKIP_EXTS = (".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".woff2", ".ico", ".gif", ".pdf", ".zip")
SKIP_PATHS = ("/cdn-cgi/", "/wp-content/", "/wp-json/", "/feed/", "/tag/", "/category/", "/author/")

def extract(text):
    phones = list(set(PHONE_PAT.findall(text)))
    emails = list(set(e for e in EMAIL_PAT.findall(text)
                       if not re.match(r'^(noreply|donotreply|no-reply|notifications|nobody|example|test|admin|root|webmaster|info|support|contact|help)@', e, re.I)))
    profs = list(set(m.group() for m in PROF_PAT.finditer(text)
                     if 8 < len(m.group()) < 80 and not m.group().startswith("Mr. ")))
    return phones, emails, profs

def should_skip(url):
    return any(url.endswith(e) for e in SKIP_EXTS) or any(p in url for p in SKIP_PATHS)

def scrape_page(page, url):
    if url in visited or len(visited) >= PAGE_LIMIT:
        return
    visited.add(url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.5)
    except Exception as e:
        print(f"  FAIL: {url[:60]} — {e}")
        return

    text = page.inner_text("body")
    phones, emails, profs = extract(text)
    title = page.title()
    entry = {"url": url, "title": title, "phones": phones, "emails": emails, "profs": profs}
    results.append(entry)
    status = f"{len(phones)}p {len(emails)}e {len(profs)}p"
    print(f"  [{len(visited):2d}/{PAGE_LIMIT}] {url[:55]:55s} {status}")

    links = page.locator("a[href]")
    count = links.count()
    found = set()
    for i in range(count):
        try:
            href = links.nth(i).get_attribute("href")
            if href:
                full = urljoin(START_URL, href)
                if full.startswith(START_URL) and full not in visited and not should_skip(full):
                    found.add(full)
        except Exception:
            pass

    for link in sorted(found):
        scrape_page(page, link)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        print(f"Crawling {START_URL} (limit {PAGE_LIMIT} pages)...\n")
        scrape_page(page, START_URL)
        browser.close()

    print(f"\n{'='*60}")
    print(f"Pages crawled: {len(visited)}, with data: {len(results)}")

    all_phones = set()
    all_emails = set()
    all_profs = []
    for r in results:
        all_phones.update(r["phones"])
        all_emails.update(r["emails"])
        all_profs.extend(r["profs"])

    print(f"\n📞 Phones ({len(all_phones)}):")
    for p in sorted(all_phones):
        print(f"  {p}")

    print(f"\n📧 Emails ({len(all_emails)}):")
    for e in sorted(all_emails):
        print(f"  {e}")

    prof_counts = Counter(all_profs)
    print(f"\n👤 Staff/Professors ({len(prof_counts)}):")
    for prof, count in prof_counts.most_common():
        print(f"  {prof}")

    with open("sbu_results.json", "w") as f:
        json.dump({"pages": results, "summary": {
            "total_phones": len(all_phones),
            "total_emails": len(all_emails),
            "total_profs": len(prof_counts),
            "phones": sorted(all_phones),
            "emails": sorted(all_emails),
            "profs": [p for p, _ in prof_counts.most_common()],
        }}, f, indent=2)
    print(f"\n💾 Saved to sbu_results.json")

if __name__ == "__main__":
    main()

