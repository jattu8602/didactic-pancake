"""
Test merge: match 10 UGC entries by name, state, pincode, city
"""
import json, re
from bs4 import BeautifulSoup

def normalize(n):
    n = n.strip().lower()
    n = re.sub(r'[^a-z0-9\s]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    for p in ['govt ', 'government ', 'shri ', 'shree ', 'smt ', 'dr ']:
        if n.startswith(p):
            n = n[len(p):]
    return n.strip()

# Parse UGC HTML
with open('data.html') as f:
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
            'status': cols[6].get_text(strip=True),
            'url': url_tag.get('href', '').strip() if url_tag else ''
        })

print(f'Total UGC: {len(ugc_list)}')

# Load existing
with open('public/data/colleges.json') as f:
    existing = json.load(f)['colleges']
print(f'Existing: {len(existing)}')

# Pick first 10 UGC entries
test = ugc_list[:10]

print(f'\n{"="*100}')
print(f'TESTING MATCHES FOR FIRST 10 UGC UNIVERSITIES')
print(f'{"="*100}')

matched_count = 0
new_count = 0

for u in test:
    u_name_norm = normalize(u['name'])
    u_state = u['state'].strip().lower()
    u_zip = u['zip'].strip()
    u_addr = u['address'].strip().lower()
    
    print(f'\n--- UGC: {u["name"]} | State: {u["state"].strip()} | Zip: {u_zip} | URL: {u["url"]}')
    
    best_match = None
    best_reason = ''
    best_score = 0
    
    for c in existing:
        score = 0
        reasons = []
        
        # 1. State match
        c_state = c.get('state', '').strip().lower()
        if u_state == c_state:
            score += 25
            reasons.append('state')
        
        # 2. Zip/pincode match
        c_zip = c.get('pin_code', '').strip()
        if u_zip and c_zip and u_zip == c_zip:
            score += 30
            reasons.append('pincode')
        
        # 3. Name overlap
        c_name_norm = normalize(c.get('name', ''))
        u_words = set(u_name_norm.split())
        c_words = set(c_name_norm.split())
        if u_words and c_words:
            overlap = u_words & c_words
            if overlap:
                name_score = len(overlap) / max(len(u_words), len(c_words)) * 40
                score += name_score
                if name_score > 10:
                    reasons.append(f'name({len(overlap)}/{len(u_words)} words)')
        
        # 4. City from address
        u_city = u_addr.split(',')[-1].strip() if ',' in u_addr else ''
        c_city = c.get('city', '').strip().lower()
        if u_city and c_city and (u_city == c_city or u_city in c_city or c_city in u_city):
            score += 15
            reasons.append('city')
        
        # 5. Address overlap
        c_addr = (c.get('address_line1', '') + ' ' + c.get('address_line2', '')).strip().lower()
        if u_addr and c_addr:
            u_addr_words = set(re.sub(r'[^a-z0-9\s]', '', u_addr).split())
            c_addr_words = set(re.sub(r'[^a-z0-9\s]', '', c_addr).split())
            if u_addr_words and c_addr_words:
                addr_overlap = u_addr_words & c_addr_words
                if len(addr_overlap) >= 2:
                    score += 10
                    reasons.append('address')
        
        if score > best_score:
            best_score = score
            best_match = c
            best_reason = ', '.join(reasons)
    
    if best_match and best_score >= 30:
        print(f'  ✓ MATCHED (score={best_score:.0f}, via {best_reason})')
        print(f'    → Existing: {best_match["name"]} | {best_match.get("city","")} | {best_match.get("pin_code","")} | Website: {best_match.get("website","")[:60]}')
        if u['url'] and not best_match.get('website'):
            print(f'    → Will ADD website: {u["url"]}')
        elif u['url'] and best_match.get('website'):
            print(f'    → Already has website: {best_match["website"][:60]}')
        matched_count += 1
    else:
        print(f'  ✗ NO MATCH (best score={best_score:.0f})')
        print(f'    → Will ADD as NEW entry')
        new_count += 1

print(f'\n{"="*100}')
print(f'SUMMARY: {matched_count} matched, {new_count} new')
print(f'Save merged output? (will be tested next)')
