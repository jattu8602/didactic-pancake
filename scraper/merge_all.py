"""
Merge all 1,293 UGC universities into colleges.json
- Match by state + pincode + name + city + address
- Add website URL to matched entries (if missing)
- Add unmatched as new entries
"""
import json, re
from bs4 import BeautifulSoup

UGC_HTML = "data.html"
EXISTING_JSON = "public/data/colleges.json"
OUTPUT = "public/data/colleges.json"

def normalize(n):
    n = n.strip().lower()
    n = re.sub(r'[^a-z0-9\s]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    for p in ['govt ', 'government ', 'shri ', 'shree ', 'smt ', 'dr ']:
        if n.startswith(p):
            n = n[len(p):]
    return n.strip()

# Parse UGC
print("Parsing UGC HTML...")
with open(UGC_HTML) as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

rows = soup.select('#tbodyuni tr')
ugc_list = []
for row in rows:
    cols = row.find_all('td')
    if len(cols) >= 8:
        url_tag = cols[7].find('a') if cols[7] else None
        ugc_list.append({
            'name': cols[2].get_text(strip=True),
            'type': cols[1].get_text(strip=True),
            'address': cols[3].get_text(strip=True),
            'zip': cols[4].get_text(strip=True),
            'state': cols[5].get_text(strip=True),
            'url': url_tag.get('href', '').strip() if url_tag else ''
        })

print(f"UGC entries: {len(ugc_list)}")

# Load existing
with open(EXISTING_JSON) as f:
    existing = json.load(f)['colleges']
print(f"Existing colleges: {len(existing)}")

# Match each UGC entry
next_id = max(int(c.get('id', 0) or 0) for c in existing) + 1
matched = 0
enriched = 0
new_entries = []

for u in ugc_list:
    u_name_norm = normalize(u['name'])
    u_state = u['state'].strip().lower()
    u_zip = u['zip'].strip()
    u_addr = u['address'].strip().lower()
    
    best = None
    best_score = 0
    
    for c in existing:
        score = 0
        
        # State
        c_state = c.get('state', '').strip().lower()
        if u_state == c_state:
            score += 25
        
        # Pincode
        c_zip = c.get('pin_code', '').strip()
        if u_zip and c_zip and u_zip == c_zip:
            score += 30
        
        # Name overlap
        c_name_norm = normalize(c.get('name', ''))
        u_words = set(u_name_norm.split())
        c_words = set(c_name_norm.split())
        if u_words and c_words:
            overlap = u_words & c_words
            if overlap:
                score += len(overlap) / max(len(u_words), len(c_words)) * 25
        
        # City
        u_city = u_addr.split(',')[-1].strip() if ',' in u_addr else ''
        c_city = c.get('city', '').strip().lower()
        if u_city and c_city and (u_city == c_city or u_city in c_city or c_city in u_city):
            score += 10
        
        # Address overlap
        c_addr = (c.get('address_line1', '') + ' ' + c.get('address_line2', '')).strip().lower()
        if u_addr and c_addr:
            u_addr_words = set(re.sub(r'[^a-z0-9\s]', '', u_addr).split())
            c_addr_words = set(re.sub(r'[^a-z0-9\s]', '', c_addr).split())
            if u_addr_words and c_addr_words:
                addr_overlap = u_addr_words & c_addr_words
                score += min(len(addr_overlap), 5) * 2
        
        if score > best_score:
            best_score = score
            best = c
    
    if best and best_score >= 30:
        # Match found
        ugc_url = u.get('url', '').strip()
        existing_url = best.get('website', '').strip()
        social_domains = {'facebook.com', 'instagram.com', 'twitter.com', 'linkedin.com', 'youtube.com'}
        
        should_update = False
        if ugc_url and not existing_url:
            should_update = True
        elif ugc_url and existing_url:
            # Check if existing is just a social media page
            try:
                from urllib.parse import urlparse
                existing_domain = urlparse(existing_url).netloc.lower().replace('www.', '')
                if existing_domain in social_domains:
                    should_update = True
            except:
                pass
        
        if should_update:
            best['website'] = ugc_url
            enriched += 1
        
        matched += 1
    else:
        # New entry
        city = ''
        addr_parts = u['address'].split(',')
        if len(addr_parts) > 1:
            city = addr_parts[-1].strip()
        
        new_entries.append({
            'id': str(next_id),
            'state': u['state'].strip(),
            'name': u['name'],
            'address_line1': u['address'],
            'address_line2': '',
            'city': city,
            'district': '',
            'pin_code': u['zip'],
            'website': u.get('url', ''),
            'phone_numbers': '',
            'emails': '',
            'professors': []
        })
        next_id += 1

# Combine
all_colleges = existing + new_entries

# Save
with open(OUTPUT, 'w') as f:
    json.dump({'colleges': all_colleges}, f, indent=2)

# Stats
states = set(c.get('state', '') for c in all_colleges)
has_website = sum(1 for c in all_colleges if c.get('website'))
has_contact = sum(1 for c in all_colleges if c.get('phone_numbers') or c.get('emails'))

print("\n" + "=" * 60)
print("MERGE COMPLETE")
print("=" * 60)
print(f"  Existing before: {len(existing)}")
print(f"  Total after:     {len(all_colleges)}")
print(f"  Matched:         {matched}")
print(f"  Website enriched: {enriched}")
print(f"  New entries:     {len(new_entries)}")
print(f"  States now:      {len(states)}")
print(f"  With website:    {has_website}")
print(f"  With contact:    {has_contact}")
print(f"\nSaved to {OUTPUT}")
