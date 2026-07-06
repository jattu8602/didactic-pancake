"""
Generic college scraper v2 — scrapes all discoverable pages for emails/phones/names.
Usage: python3 scrape_generic.py --name "College Name" --url "https://..." --output "/output"
"""
import re, json, sys, os, time
import argparse
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--url', required=True)
parser.add_argument('--output', default='/output')
args = parser.parse_args()

NAME = args.name
START_URL = args.url
OUTPUT_DIR = args.output
MAX_PAGES = 40
MAX_LISTING = 15

PROFILE_KEYWORDS = ['/faculty/', '/profile/', '/staff/', '/people/', '/teacher/', '/member/',
                    '/professor/', '/dean/', '/director/', '/hod/', '/team/', '/employee/',
                    '/academic-staff/', '/teaching-staff/', '/our-staff/', '/personnel/']

PAGE_KEYWORDS = ['faculty', 'people', 'professor', 'staff', 'teacher', 'directory',
                 'department', 'dept', 'school', 'our-team', 'academic', 'contact',
                 'about', 'phone', 'email', 'find-people', 'person']

EMAIL_PAT = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_PAT = re.compile(r'(?:\+?91[-.\s]?)?[6789]\d{9}|\+\d{1,3}\s?\(?\d{1,4}\)?[-.\s]?\d{6,8}')
OBFUSCATED_EMAIL = re.compile(r'([a-zA-Z0-9._%+-]+)\s*\(?\[?at\]?\)?\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')
DR_PREFIX = re.compile(r'(Dr\.?\s*|Prof\.?\s*|Mr\.?\s*|Ms\.?\s*|Mrs\.?\s*)', re.I)
NAME_IN_PAREN = re.compile(r'\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\)')

BAD_EMAILS = {
    'glyc@ion.physiologia', 'www.researchg@e.net', 'allegralabor@ory.net',
    'institute-for-private-intern@ional-law-in-africa.aspx'
}

def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] [{NAME}] {msg}', flush=True)

def clean_email(e):
    e = e.lower().strip('.')
    if re.search(r'\.(png|jpg|jpeg|gif|css|js|svg|ico)$', e): return None
    if re.match(r'^(noreply|donotreply|no-reply|notifications|nobody|example|test|admin|root|webmaster|wordpress|support|info|contact|help)@', e): return None
    if e in BAD_EMAILS: return None
    if 'researchgate' in e or 'facebook' in e or 'twitter' in e: return None
    if len(e) > 5 and '@' in e and e.count('@') == 1: return e
    return None

def extract_emails(text):
    found = set()
    for m in EMAIL_PAT.finditer(text):
        e = clean_email(m.group())
        if e: found.add(e)
    for m in OBFUSCATED_EMAIL.finditer(text):
        e = clean_email(f'{m.group(1)}@{m.group(2)}')
        if e: found.add(e)
    return found

def extract_phones(text):
    found = set()
    for m in PHONE_PAT.finditer(text):
        d = re.sub(r'[\s\-.)(]', '', m.group())
        if re.match(r'^97[89]\d{10}$', d): continue
        if 10 <= len(d) <= 15: found.add(d)
    return found

def extract_nearby_name(text, email_pos, window=400):
    """Try to find a person's name near an email address in text."""
    start = max(0, email_pos - window)
    end = min(len(text), email_pos + 100)
    snippet = text[start:end]
    
    # Remove email itself
    snippet_clean = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '', snippet)
    
    # Try to find "Name (email)" pattern
    for m in NAME_IN_PAREN.finditer(snippet):
        name = m.group(1)
        if 5 < len(name) < 50:
            return name
    
    # Try to find name on lines before email
    lines = snippet.split('\n')
    for line in lines[-5:]:
        line = line.strip()
        # Skip if the line contains the email itself
        if '@' in line: continue
        # Match "Dr. Name" or "Prof. Name" or just "Name"
        m = re.search(r'(Dr\.?\s*|Prof\.?\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', line)
        if m:
            name = (m.group(1) or '') + m.group(2)
            name = name.strip().rstrip(',.')
            if 5 < len(name) < 50 and not re.match(r'^(Home|About|Contact|Email|Phone|Search|Skip|Copyright|All|Powered|Map|Location|Faqs|Portal|Box|Quick|Menu|Skip|Log|Sign|Register)', name, re.I):
                return name
    
    return None

def get_internal_links(page, base_url):
    links = set()
    base_domain = urlparse(base_url).netloc.replace('www.', '')
    for a in page.query_selector_all('a[href]'):
        href = a.get_attribute('href')
        if not href or href.startswith('#') or href.startswith('javascript') or href.startswith('mailto'):
            continue
        full = urljoin(base_url, href)
        domain = urlparse(full).netloc.replace('www.', '')
        if domain == base_domain or domain.endswith('.' + base_domain):
            links.add(full)
    return links

def scrape():
    log(f"Starting scrape of {NAME}")
    log(f"URL: {START_URL}")
    
    result = {
        'university': NAME,
        'url': START_URL,
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
        
        # Step 1: Homepage
        log("Step 1: Homepage...")
        scraped_urls = set()
        to_visit = []
        
        try:
            page.goto(START_URL, wait_until='domcontentloaded', timeout=30000)
            time.sleep(2)
            result['pages_scraped'] += 1
            text = page.inner_text('body')
            all_emails.update(extract_emails(text))
            all_phones.update(extract_phones(text))
            
            all_links = get_internal_links(page, START_URL)
            log(f"  Found {len(all_links)} internal links")
            
            # Prioritize: profile URLs first, then listing pages, then rest
            profile_urls = {l for l in all_links if any(kw in l.lower() for kw in PROFILE_KEYWORDS)}
            listing_urls = {l for l in all_links if any(kw in l.lower() for kw in PAGE_KEYWORDS) and l not in profile_urls}
            other_urls = all_links - profile_urls - listing_urls
            
            to_visit = list(profile_urls) + list(listing_urls) + list(other_urls)
            log(f"  Profile: {len(profile_urls)}, Listing: {len(listing_urls)}, Other: {len(other_urls)}")
            
        except Exception as e:
            log(f"  ERROR: {str(e)[:80]}")
            result['errors'].append(f"Homepage: {str(e)[:80]}")
            to_visit = []
        
        # Step 2: Scrape pages
        log(f"\nStep 2: Scraping up to {MAX_PAGES} pages...")
        page_count = 0
        
        for url in to_visit:
            if url in scraped_urls or page_count >= MAX_PAGES:
                continue
            scraped_urls.add(url)
            
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=25000)
                time.sleep(1.5)
                result['pages_scraped'] += 1
                page_count += 1
                
                text = page.inner_text('body')
                html = page.content()
                
                emails = extract_emails(text)
                phones = extract_phones(text)
                all_emails.update(emails)
                all_phones.update(phones)
                
                # Method 1: Find mailto links in HTML -> these directly link to people
                for m in re.finditer(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html):
                    email = clean_email(m.group(1))
                    if not email: continue
                    all_emails.add(email)
                    
                    # Find name from nearby HTML
                    nearby = html[max(0, m.start()-400):m.end()+100]
                    n_match = re.search(r'(Dr\.?\s*|Prof\.?\s*|Mr\.?\s*|Ms\.?\s*|Mrs\.?\s*)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', nearby)
                    name = None
                    if n_match:
                        candidate = (n_match.group(1) or '') + n_match.group(2)
                        candidate = candidate.strip().rstrip(',.')
                        if 5 < len(candidate) < 60 and not re.match(r'^(Home|About|Contact|Email|Phone|Search|Skip|Copyright|All|Powered)', candidate, re.I):
                            name = candidate
                    
                    if name:
                        if name not in profs:
                            profs[name] = {'name': name, 'email': email, 'phone': ''}
                            log(f"    + {name} <{email}>")
                        else:
                            existing = profs[name]['email']
                            if email not in existing:
                                profs[name]['email'] = '; '.join([existing, email])
                
                # Method 2: Find emails in text and try to find nearby names
                for m in EMAIL_PAT.finditer(text):
                    email = clean_email(m.group())
                    if not email or email in {e for p in profs.values() for e in p.get('email', '').split('; ')}:
                        continue
                    
                    name = extract_nearby_name(text, m.start())
                    if name:
                        all_emails.add(email)
                        if name not in profs:
                            profs[name] = {'name': name, 'email': email, 'phone': ''}
                            log(f"    + {name} <{email}>")
                        else:
                            existing = profs[name]['email']
                            if email not in existing:
                                profs[name]['email'] = '; '.join([existing, email])
                
                # Discover more links from this page
                if page_count < MAX_PAGES:
                    more_links = get_internal_links(page, url) - scraped_urls
                    # Add new links to the end of the queue (only if they look interesting)
                    for l in more_links:
                        if l not in scraped_urls and l not in to_visit:
                            if any(kw in l.lower() for kw in PAGE_KEYWORDS + PROFILE_KEYWORDS):
                                to_visit.append(l)
                
                status = f"e:{len(emails)} p:{len(phones)}" if emails or phones else "(no data)"
                log(f"  [{page_count}/{MAX_PAGES}] {urlparse(url).path[:40] or '/'} -> {status}")
                
            except Exception as e:
                log(f"  [{page_count+1}] {urlparse(url).path[:40]} -> ERROR: {str(e)[:60]}")
        
        browser.close()
    
    # Filter out non-professor names
    skip_names = set()
    professor_list = []
    for name, data in sorted(profs.items()):
        # Skip navigation items, addresses, etc.
        if len(name) < 6: continue
        if re.match(r'^(Home|About|Contact|Email|Phone|Search|Skip|Copyright|All|Powered|Map|Location|Faqs|Portal|Box|Quick|Menu|Log|Sign|Register|Apply|Prospectus|Alumni|Placement|Tender|Notice|Event|News|Blog|Gallery|Video|Downloads|Forms|Policies|Committee|Council|Cell|Club|Society|Program|Course|Fee|Hostel|Library|Sports|NSS|NCC)', name, re.I): continue
        if re.match(r'^[A-Z][a-z]+ [A-Z][a-z]+ [A-Z][a-z]+ [A-Z][a-z]+ [A-Z][a-z]+', name): continue  # Too many words
        if re.search(r'(University|College|School|Department|Faculty|Campus|Road|Nag?r|Delhi|Marga|Hostel|Office|Section|Committee)$', name): continue
        professor_list.append(data)
    
    result['professors'] = professor_list
    result['total_professors'] = len(professor_list)
    result['total_emails'] = len(all_emails)
    result['total_phones'] = len(all_phones)
    result['all_emails'] = sorted(all_emails)
    result['all_phones'] = sorted(all_phones)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    safe_name = re.sub(r'[^a-zA-Z0-9]+', '_', NAME.lower()).strip('_')
    outpath = os.path.join(OUTPUT_DIR, f'{safe_name}.json')
    with open(outpath, 'w') as f:
        json.dump(result, f, indent=2)
    
    log(f"\n{'='*50}")
    log(f"SCRAPE COMPLETE")
    log(f"{'='*50}")
    log(f"Pages: {result['pages_scraped']}")
    log(f"Professors: {result['total_professors']}")
    log(f"Emails: {result['total_emails']}")
    log(f"Phones: {result['total_phones']}")
    log(f"Saved: {outpath}")
    log(f"Errors: {len(result['errors'])}")
    
    return result

if __name__ == '__main__':
    result = scrape()
    sys.exit(0 if not result['errors'] else 1)
