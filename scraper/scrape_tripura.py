"""
Tripura college scraper — crawls all pages for emails, phones, professor names.
Site-specific URL paths for each college.
"""
import re, json, sys, os, time, argparse
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

SITES = {
    "The ICFAI University Tripura": {
        "url": "https://www.iutripura.edu.in/",
        "paths": ["/", "/faculty", "/contact-us", "/contact", "/about-us", "/administration", "/departments"]
    },
    "Tripura University": {
        "url": "https://tripurauniv.ac.in/",
        "paths": ["/", "/contact", "/faculty", "/departments", "/teaching-faculty-list"],
        "full_pages": [
            "/site/index.php/en/teaching-faculty-list-en",
            "/site/index.php/en/tu-contact-us-en/tu-contact-information-en",
        ]
    },
    "Maharaja Bir Bikram University": {
        "url": "https://mbbuniversity.ac.in/",
        "paths": ["/", "/contact-us", "/faculty", "/about/contact", "/en/faculty"]
    },
    "Mata Tripura Sundari Open University": {
        "url": "https://www.mtsou.edu.in/",
        "paths": ["/", "/contact-us", "/about-us", "/faculty", "/team"]
    },
    "National Law University Tripura": {
        "url": "https://nlutripura.ac.in/",
        "paths": ["/", "/contact-us", "/faculty", "/people", "/about-nlut"]
    },
    "Techno India University Tripura": {
        "url": "https://www.tiut.ac.in/",
        "paths": ["/", "/contact", "/contacts", "/faculty", "/faculties", "/about-us", "/departments"]
    },
    "The Aryavart International University": {
        "url": "https://aiuniversity.edu.in/",
        "paths": ["/", "/contact-us", "/contact", "/faculty"]
    },
    "The Dhamma Dipa International Buddhist University": {
        "url": "https://www.ddibu.in/",
        "paths": ["/", "/contact", "/page/about-university", "/page/faculty"]
    },
}

EMAIL_PAT = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_PAT = re.compile(r'(?:\+?91[-.\s]?)?[6789]\d{9}')
AT_OBFUSCATION = re.compile(r'([a-zA-Z0-9._%+-]+)\s*\[?\s*at\s*\]?\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', re.I)
DOT_OBFUSCATION = re.compile(r'([a-zA-Z0-9._%+-]+)\s*\[?\s*dot\s*\]?\s*([a-zA-Z]{2,})', re.I)

BAD_EMAILS = {
    'glyc@ion.physiologia', 'www.researchg@e.net', 'allegralabor@ory.net',
    'institute-for-private-intern@ional-law-in-africa.aspx'
}

def log(name, msg):
    print(f'[{time.strftime("%H:%M:%S")}] [{name}] {msg}', flush=True)

def clean_email(e):
    e = e.lower().strip('.')
    if re.search(r'\.(png|jpg|jpeg|gif|css|js|svg|ico|pdf)$', e): return None
    if re.match(r'^(noreply|donotreply|no-reply|notifications|nobody|example|test)', e): return None
    if e in BAD_EMAILS: return None
    if any(s in e for s in ['researchgate', 'facebook', 'twitter', 'linkedin', 'instagram']): return None
    if ' ' in e: return None
    if len(e) > 5 and '@' in e and e.count('@') == 1: return e
    return None

def extract_emails(text):
    found = set()
    for m in EMAIL_PAT.finditer(text):
        e = clean_email(m.group())
        if e: found.add(e)
    for m in AT_OBFUSCATION.finditer(text):
        e = clean_email(f'{m.group(1)}@{m.group(2)}')
        if e: found.add(e)
    # [at] variants
    for m in re.finditer(r'([a-zA-Z0-9._%+-]+)\s*\(at\)\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', text, re.I):
        e = clean_email(f'{m.group(1)}@{m.group(2)}')
        if e: found.add(e)
    return found

def extract_phones(text):
    found = set()
    for m in PHONE_PAT.finditer(text):
        d = re.sub(r'[\s\-.)(]', '', m.group())
        if re.match(r'^97[89]\d{10}$', d): continue
        if 10 <= len(d) <= 15 and d.startswith(('91', '6', '7', '8', '9')): found.add(d)
    return found

def extract_prof_names(text):
    """Find professor names with titles."""
    names = set()
    for m in re.finditer(r'(?:(?:Dr|Prof|Professor|Mr|Ms|Mrs)\.?\s*)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', text):
        name = m.group(0).strip()
        if 5 < len(name) < 60:
            names.add(name)
    return names

def scrape_site(name, config, output_dir):
    log(name, f"Starting scrape of {config['url']}")
    result = {
        'university': name,
        'url': config['url'],
        'pages_scraped': 0,
        'professors': [],
        'all_emails': [],
        'all_phones': [],
        'errors': []
    }
    profs = {}
    all_emails = set()
    all_phones = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        page = browser.new_page()
        visited = set()
        
        urls_to_scrape = []
        for path in config.get('paths', []) + config.get('full_pages', []):
            if path.startswith('/'):
                urls_to_scrape.append(config['url'].rstrip('/') + path)
            else:
                urls_to_scrape.append(path)

        for url in urls_to_scrape:
            if url in visited: continue
            visited.add(url)
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=45000)
                time.sleep(2)
                result['pages_scraped'] += 1
                text = page.inner_text('body')
                html = page.content()

                emails = extract_emails(text)
                phones = extract_phones(text)
                all_emails.update(emails)
                all_phones.update(phones)
                
                names = extract_prof_names(text)
                
                # Find mailto links
                for m in re.finditer(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html):
                    email = clean_email(m.group(1))
                    if not email: continue
                    all_emails.add(email)
                    nearby = html[max(0, m.start()-500):m.end()+200]
                    n_match = re.search(r'(Dr\.?\s*|Prof\.?\s*|Mr\.?\s*|Ms\.?\s*|Mrs\.?\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', nearby)
                    if n_match:
                        candidate = ((n_match.group(1) or '') + n_match.group(2)).strip().rstrip(',.')
                        if 5 < len(candidate) < 60:
                            if candidate not in profs:
                                profs[candidate] = {'name': candidate, 'email': email, 'phone': ''}
                                log(name, f"  + {candidate} <{email}>")
                
                # Associate emails with names using table structures
                for email in emails:
                    email_escaped = re.escape(email)
                    # Find email in HTML and look at surrounding context
                    for em in re.finditer(email_escaped, html):
                        nearby = html[max(0, em.start()-600):em.end()+200]
                        rows = re.split(r'</tr>|<br>|<div[^>]*>', nearby)
                        for row in rows:
                            n_match = re.search(r'(Dr\.?\s*|Prof\.?\s*|Mr\.?\s*|Ms\.?\s*|Mrs\.?\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', row)
                            if n_match:
                                candidate = ((n_match.group(1) or '') + n_match.group(2)).strip().rstrip(',.')
                                if 5 < len(candidate) < 60 and '@' not in candidate and not re.match(r'^(Phone|Email|Contact|Home|About|Name|Designation|Specialization)', candidate, re.I):
                                    if candidate not in profs:
                                        profs[candidate] = {'name': candidate, 'email': '', 'phone': ''}
                                    existing = profs[candidate]['email']
                                    if email not in existing:
                                        profs[candidate]['email'] = email if not existing else '; '.join([existing, email])
                                    log(name, f"  + {candidate} <{email}>")
                                    break

                # Associate phones with names
                for phone in phones:
                    phone_escaped = re.escape(phone)
                    for pm in re.finditer(phone_escaped, html):
                        nearby = html[max(0, pm.start()-400):pm.end()+200]
                        n_match = re.search(r'(Dr\.?\s*|Prof\.?\s*|Mr\.?\s*|Ms\.?\s*|Mrs\.?\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', nearby)
                        if n_match:
                            candidate = ((n_match.group(1) or '') + n_match.group(2)).strip().rstrip(',.')
                            if 5 < len(candidate) < 60 and '@' not in candidate:
                                if candidate in profs:
                                    existing_phone = profs[candidate]['phone']
                                    if phone not in existing_phone:
                                        profs[candidate]['phone'] = phone if not existing_phone else '; '.join([existing_phone, phone])

                # Discover more links from this page
                if result['pages_scraped'] < 30:
                    for a in page.query_selector_all('a[href]'):
                        href = a.get_attribute('href')
                        if not href or href.startswith('#') or href.startswith('javascript') or href.startswith('mailto'):
                            continue
                        full = urljoin(url, href)
                        up = urlparse(full)
                        base_domain = urlparse(config['url']).netloc.replace('www.', '')
                        domain = up.netloc.replace('www.', '')
                        if domain == base_domain or domain.endswith('.' + base_domain):
                            interesting = ['faculty', 'professor', 'staff', 'teacher', 'department', 'dept', 'contact', 'people', 'directory', 'profile', 'academic', 'team', 'personnel', 'about', 'administration', 'hod', 'dean', 'director']
                            if any(k in up.path.lower() for k in interesting):
                                if full not in visited:
                                    visited.add(full)
                                    urls_to_scrape.append(full)

                log(name, f"  [{result['pages_scraped']}] {urlparse(url).path[:50]} -> e:{len(emails)} p:{len(phones)} n:{len(names)}")
            except Exception as e:
                log(name, f"  {urlparse(url).path[:50]} -> ERROR: {str(e)[:80]}")
                result['errors'].append(f"{url}: {str(e)[:80]}")

        browser.close()

    # Filter and finalize
    skip_patterns = re.compile(r'^(Home|About|Contact|Email|Phone|Search|Skip|Copyright|Powered|Map|Location|Faqs|Portal|Quick|Menu|Log|Sign|Register|Apply|Prospectus|Alumni|Placement|Tender|Notice|Event|News|Blog|Gallery|Video|Download|Admission|Program|Course|Fee|Hostel|Library|Sports|Student)', re.I)
    professor_list = []
    for name_key, data in sorted(profs.items()):
        if len(name_key) < 6: continue
        if skip_patterns.match(name_key): continue
        if re.search(r'(University|College|School|Department|Faculty|Campus|Road|Nagar|Marg|Hostel|Office|Section|Committee|Building)$', name_key): continue
        professor_list.append(data)

    result['professors'] = professor_list
    result['total_professors'] = len(professor_list)
    result['total_emails'] = len(all_emails)
    result['total_phones'] = len(all_phones)
    result['all_emails'] = sorted(all_emails)
    result['all_phones'] = sorted(all_phones)

    os.makedirs(output_dir, exist_ok=True)
    safe = re.sub(r'[^a-zA-Z0-9]+', '_', name.lower()).strip('_')
    outpath = os.path.join(output_dir, f'{safe}.json')
    with open(outpath, 'w') as f:
        json.dump(result, f, indent=2)

    log(name, f"\n{'='*40}")
    log(name, f"COMPLETE: {result['total_professors']} profs, {result['total_emails']} emails, {result['total_phones']} phones")
    log(name, f"Saved: {outpath}")
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--output', default='/output')
    args = parser.parse_args()

    if args.name not in SITES:
        print(f"Unknown site: {args.name}. Options: {list(SITES.keys())}")
        sys.exit(1)

    config = SITES[args.name]
    result = scrape_site(args.name, config, args.output)
    sys.exit(0 if not result['errors'] else 1)
