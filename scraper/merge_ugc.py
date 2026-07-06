"""
Merge 1,293 UGC universities into colleges.json
- Match existing entries by state + name similarity
- Enrich matched entries with UGC website URL
- Add unmatched as new entries
- Scrape websites for phones/emails (concurrent)
"""
import json, re, csv, os, sys
import requests
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from bs4 import BeautifulSoup

UGC_HTML = "../data.html"
EXISTING_JSON = "../public/data/colleges.json"
OUTPUT = "../public/data/colleges.json"
MAX_WORKERS = 15
REQUEST_TIMEOUT = 10

sys.path.insert(0, os.path.dirname(__file__))

def normalize(n):
    n = n.strip().lower()
    n = re.sub(r'[^a-z0-9\s]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    for p in ['govt ', 'government ', 'shri ', 'shree ', 'smt ', 'dr ', '\u201c', '\u201d', '"', '"']:
        n = n.replace(p, '')
    return n.strip()

def parse_ugc_html():
    with open(UGC_HTML) as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    rows = soup.select('#tbodyuni tr')
    universities = []
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 8:
            url_tag = cols[7].find('a') if cols[7] else None
            url = url_tag.get('href', '').strip() if url_tag else ''
            universities.append({
                'name': cols[2].get_text(strip=True),
                'type': cols[1].get_text(strip=True),
                'address': cols[3].get_text(strip=True),
                'zip': cols[4].get_text(strip=True),
                'state': cols[5].get_text(strip=True),
                'status': cols[6].get_text(strip=True),
                'url': url
            })
    return universities

def load_existing():
    with open(EXISTING_JSON) as f:
        return json.load(f)['colleges']

def match_ugc_to_existing(ugc_list, existing_colleges):
    matched = []
    unmatched = []
    next_id = max(int(c.get('id', 0) or 0) for c in existing_colleges) + 1
    
    for u in ugc_list:
        u_name = normalize(u['name'])
        u_state = u['state'].strip().lower()
        u_words = set(u_name.split())
        
        best = None
        best_score = 0
        if len(u_words) >= 2:
            for c in existing_colleges:
                c_name = normalize(c.get('name', ''))
                c_state = c.get('state', '').strip().lower()
                if u_state != c_state:
                    continue
                c_words = set(c_name.split())
                if not c_words:
                    continue
                overlap = len(u_words & c_words)
                score = overlap / min(len(u_words), len(c_words))
                if score > best_score:
                    best_score = score
                    best = c
        
        if best and best_score >= 0.5:
            matched.append((u, best))
        else:
            # Create new entry
            city = ''
            addr_parts = u.get('address', '').split(',')
            if len(addr_parts) > 1:
                city = addr_parts[-1].strip()
            
            new_entry = {
                'id': str(next_id),
                'state': u['state'].strip(),
                'name': u['name'],
                'address_line1': u.get('address', ''),
                'address_line2': '',
                'city': city,
                'district': '',
                'pin_code': u.get('zip', ''),
                'website': u.get('url', ''),
                'phone_numbers': '',
                'emails': '',
                'professors': [],
                '_ugc_id': u.get('url', '')  # temp marker
            }
            next_id += 1
            unmatched.append(new_entry)
    
    return matched, unmatched

def scrape_site(url, timeout=REQUEST_TIMEOUT):
    """Scrape a single website for phones and emails."""
    result = {'phones': [], 'emails': []}
    if not url:
        return result
    
    try:
        r = requests.get(url, timeout=timeout, 
                        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'},
                        allow_redirects=True)
        if r.status_code != 200:
            return result
        
        soup = BeautifulSoup(r.text, 'html.parser')
        text = soup.get_text()
        
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        phones = re.findall(r'(?:\+?91[-.\s]?)?[6789]\d{9}', text)
        phones += re.findall(r'0\d{2,4}[-.\s]?\d{6,8}', text)
        
        result['emails'] = list(set(e.lower() for e in emails 
                                   if not e.lower().endswith(('.png', '.jpg', '.gif', '.css', '.js', '.svg'))))
        result['phones'] = list(set(p for p in phones if len(re.sub(r'[\s\-.]', '', p)) >= 10))
        
        # Also check contact/about pages
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            if any(kw in href for kw in ['contact', 'about-us', 'about', 'phone', 'telephone']):
                link = urljoin(url, a['href'])
                try:
                    cr = requests.get(link, timeout=timeout,
                                     headers={'User-Agent': 'Mozilla/5.0'},
                                     allow_redirects=True)
                    if cr.status_code == 200:
                        ct = BeautifulSoup(cr.text, 'html.parser').get_text()
                        result['emails'].extend(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', ct))
                        result['phones'].extend(re.findall(r'(?:\+?91[-.\s]?)?[6789]\d{9}', ct))
                        result['phones'].extend(re.findall(r'0\d{2,4}[-.\s]?\d{6,8}', ct))
                except:
                    pass
                break  # Just check first contact page
        
        result['emails'] = list(set(result['emails']))
        result['phones'] = list(set(p for p in result['phones'] if len(re.sub(r'[\s\-.]', '', p)) >= 10))
        
    except Exception:
        pass
    
    return result

def main():
    print("=" * 60)
    print("UGC Merge + Scrape")
    print("=" * 60)
    
    # Parse
    print("\n[1/4] Parsing UGC HTML...")
    ugc_list = parse_ugc_html()
    print(f"  Parsed {len(ugc_list)} universities")
    
    # Load existing
    print("\n[2/4] Loading existing colleges...")
    existing = load_existing()
    print(f"  Existing: {len(existing)} colleges")
    
    # Match
    print("\n[3/4] Cross-referencing...")
    matched, new_entries = match_ugc_to_existing(ugc_list, existing)
    print(f"  Matched (enriched): {len(matched)}")
    print(f"  New entries to add: {len(new_entries)}")
    
    # Enrich matched entries with UGC data
    enriched_count = 0
    for u, c in matched:
        ugc_url = u.get('url', '').strip()
        existing_url = c.get('website', '').strip()
        if ugc_url and not existing_url:
            c['website'] = ugc_url
            enriched_count += 1
    print(f"  Enriched {enriched_count} existing entries with website URL")
    
    # Build final list: existing (enriched) + new
    all_colleges = existing + new_entries
    
    # Scrape websites
    print("\n[4/4] Scraping websites for contact info...")
    to_scrape = []
    for c in all_colleges:
        url = c.get('website', '').strip()
        has_contact = bool(c.get('phone_numbers') or c.get('emails'))
        if url and not has_contact:
            to_scrape.append((c, url))
    
    print(f"  Websites to scrape: {len(to_scrape)}")
    
    scraped_phones = 0
    scraped_emails = 0
    scraped_with_data = 0
    
    def scrape_one(item):
        college, url = item
        result = scrape_site(url)
        return college, result
    
    batch_size = 200
    for batch_start in range(0, len(to_scrape), batch_size):
        batch = to_scrape[batch_start:batch_start + batch_size]
        print(f"  Scraping batch {batch_start//batch_size + 1}/{(len(to_scrape)-1)//batch_size + 1} ({len(batch)} sites)...")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(scrape_one, item): item for item in batch}
            for future in as_completed(futures):
                try:
                    college, result = future.result()
                    if result['emails']:
                        college['emails'] = '; '.join(result['emails'][:5])
                        scraped_emails += len(result['emails'])
                    if result['phones']:
                        college['phone_numbers'] = '; '.join(result['phones'][:5])
                        scraped_phones += len(result['phones'])
                    if result['emails'] or result['phones']:
                        scraped_with_data += 1
                except Exception:
                    pass
    
    # Clean up temp field
    for c in all_colleges:
        c.pop('_ugc_id', None)
    
    # Save
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump({'colleges': all_colleges}, f, indent=2)
    
    # Stats
    total_after = len(all_colleges)
    has_contact = sum(1 for c in all_colleges if c.get('phone_numbers') or c.get('emails'))
    has_website = sum(1 for c in all_colleges if c.get('website'))
    states = set(c.get('state', '') for c in all_colleges)
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Total before: {len(existing)} colleges")
    print(f"  Total after:  {total_after} colleges")
    print(f"  New entries added: {len(new_entries)}")
    print(f"  Existing enriched: {enriched_count}")
    print(f"  States represented: {len(states)}")
    print(f"  With website: {has_website}")
    print(f"  With phone/email: {has_contact}")
    print(f"  Scraped fresh data: {scraped_with_data} sites")
    print(f"  Phones found: {scraped_phones}")
    print(f"  Emails found: {scraped_emails}")
    print(f"\nSaved to {OUTPUT}")

if __name__ == '__main__':
    main()
