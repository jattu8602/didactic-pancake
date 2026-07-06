"""
Scrape South Asian University (https://sau.int/) — all professors, phones, emails.
"""
import re, json, time
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

FACULTY_PAGES = [
    "https://sau.int/faculty-members/",
    "https://sau.int/faculty-of-economics-fe/fe-faculty/",
    "https://sau.int/faculty-of-legal-studies-fls/faculty/",
    "https://sau.int/faculty-of-life-sciences-biotechnology-flsb/flsb-faculty/",
    "https://sau.int/faculty-of-management/faculty-members/",
    "https://sau.int/department-of-computer-science-and-engineering/faculty-of-cs/",
    "https://sau.int/department-of-international-relations/faculty/",
    "https://sau.int/department-of-mathematics/faculty/",
    "https://sau.int/department-of-sociology/faculty/",
]

SKIP_PROF = re.compile(
    r'^(search|home|about|contact|login|register|intranet|tenders|career|people|media|student|research|admission|facult|copyright|all rights|powered|map|location|university|college|school)', re.I
)

def is_valid_name(name):
    name = name.strip().rstrip(',')
    if not name or len(name) < 5:
        return False
    if SKIP_PROF.match(name):
        return False
    if not re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4}$', name):
        return False
    return True

def extract_phones(text):
    found = set()
    for pat in [
        r'(?:\+?91[-.\s]?)?[6789]\d{9}',
        r'0\d{2,4}[-.\s]?\d{6,8}',
        r'\+\d{1,3}\s?\(?\d{1,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4,8}',
        r'\+\d{1,3}\s?\(?\d{1,4}\)?[-.\s]?\d{6,8}',
    ]:
        for m in re.finditer(pat, text):
            digits = re.sub(r'[\s\-.)(]', '', m.group())
            # Skip ISBNs (978/979 prefix, 13 digits)
            if re.match(r'^978\d{10}$', digits) or re.match(r'^979\d{10}$', digits):
                continue
            if 10 <= len(digits) <= 15:
                found.add(digits)
    return sorted(found)

def extract_emails(text, html=''):
    found = set()
    
    # Standard email format
    for m in re.finditer(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text):
        e = m.group().lower().strip('.')
        if re.search(r'\.(png|jpg|jpeg|gif|css|js|svg|ico)$', e, re.I): continue
        if re.match(r'^(noreply|donotreply|no-reply|notifications|nobody|example|test|admin|root|webmaster|wordpress|support|info|contact)@', e, re.I): continue
        if len(e) > 5 and '@' in e:
            found.add(e)
    
    # Obfuscated email: name(at)domain or name[at]domain or name (at) domain
    for m in re.finditer(r'([a-zA-Z0-9._%+-]+)\s*\(?\[?at\]?\)?\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text):
        e = f'{m.group(1)}@{m.group(2)}'.lower().strip('.')
        if len(e) > 5 and '@' in e:
            found.add(e)
    
    # Also extract from mailto: links in HTML
    if html:
        for m in re.finditer(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html):
            e = m.group(1).lower().strip('.')
            if len(e) > 5 and '@' in e:
                found.add(e)
    
    return sorted(found)

def scrape():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        professors = {}
        all_phones = set()
        all_emails = set()
        pages_scraped = 0
        
        # Step 1: Go through each faculty page and collect profile links
        profile_links = set()
        for url in FACULTY_PAGES:
            try:
                print(f"[Listing] {url}")
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                time.sleep(2)
                pages_scraped += 1
                
                # Find all faculty profile links
                links = page.query_selector_all('a[href*="/faculty/"]')
                for link in links:
                    href = link.get_attribute('href')
                    if href and '/faculty/' in href:
                        name = link.inner_text().strip()
                        if is_valid_name(name):
                            profile_links.add((name, urljoin(url, href)))
                
                # Also extract emails/phones from listing page
                html = page.content()
                text = page.inner_text('body')
                all_phones.update(extract_phones(text))
                all_emails.update(extract_emails(text, html))
                
                print(f"  -> Found {len(links)} faculty links (after filter: {sum(1 for n,_ in profile_links if True)})")
                
            except Exception as e:
                print(f"  ERROR: {e}")
        
        print(f"\nTotal unique professor profiles to visit: {len(profile_links)}")
        
        # Step 2: Visit each profile page
        for i, (name, url) in enumerate(sorted(profile_links)):
            try:
                print(f"  [{i+1}/{len(profile_links)}] {name}")
                page.goto(url, wait_until='domcontentloaded', timeout=20000)
                time.sleep(1.5)
                pages_scraped += 1
                
                html = page.content()
                text = page.inner_text('body')
                phones = extract_phones(text)
                emails = extract_emails(text, html)
                
                all_phones.update(phones)
                all_emails.update(emails)
                
                # Check for name variations
                page_title = page.title()
                
                prof = {
                    'name': name,
                    'email': '; '.join(emails) if emails else '',
                    'phone': '; '.join(phones) if phones else ''
                }
                
                if name not in professors:
                    professors[name] = prof
                else:
                    existing = professors[name]
                    if prof['email'] and prof['email'] not in existing['email']:
                        existing['email'] = '; '.join(filter(None, [existing['email'], prof['email']]))
                    if prof['phone'] and prof['phone'] not in existing['phone']:
                        existing['phone'] = '; '.join(filter(None, [existing['phone'], prof['phone']]))
                
                status = f"e:{len(emails)} p:{len(phones)}" if emails or phones else "(no contact)"
                print(f"    -> {status}")
                
            except Exception as e:
                print(f"    ERROR: {e}")
        
        browser.close()
        
        # Step 3: Also scrape contact page
        try:
            page = browser.new_page()
            page = browser.new_page()
            page.goto('https://sau.int/contact/', wait_until='domcontentloaded', timeout=20000)
            time.sleep(1)
            html = page.content()
            text = page.inner_text('body')
            all_phones.update(extract_phones(text))
            all_emails.update(extract_emails(text, html))
            pages_scraped += 1
            browser.close()
        except:
            pass
        
        # Build result
        prof_list = [v for v in professors.values()]
        
        result = {
            'university': 'South Asian University',
            'state': 'Delhi',
            'url': 'https://sau.int/',
            'pages_scraped': pages_scraped,
            'total_professors': len(prof_list),
            'total_phones': len(all_phones),
            'total_emails': len(all_emails),
            'phones': sorted(all_phones),
            'emails': sorted(all_emails),
            'professors': prof_list
        }
        
        return result

if __name__ == '__main__':
    result = scrape()
    
    print("\n" + "=" * 60)
    print("SAU SCRAPE RESULTS")
    print("=" * 60)
    print(f"Pages scraped:    {result['pages_scraped']}")
    print(f"Professors found: {result['total_professors']}")
    print(f"Unique phones:    {result['total_phones']}")
    print(f"Unique emails:    {result['total_emails']}")
    
    if result['phones']:
        print(f"\nPhones ({len(result['phones'])}):")
        for p in result['phones']:
            print(f"  {p}")
    else:
        print("\nNo phones found")
    
    if result['emails']:
        print(f"\nEmails ({len(result['emails'])}):")
        for e in result['emails']:
            print(f"  {e}")
    else:
        print("\nNo emails found")
    
    print(f"\nProfessors ({len(result['professors'])}):")
    for p in result['professors'][:20]:
        print(f"  {p['name']:40s} | email: {p['email'][:40] if p['email'] else '':40s} | phone: {p['phone'][:20] if p['phone'] else ''}")
    if len(result['professors']) > 20:
        print(f"  ... and {len(result['professors']) - 20} more")
    
    with open('public/data/sau_scraped.json', 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to public/data/sau_scraped.json")
