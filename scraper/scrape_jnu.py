"""
JNU scraper - extracts faculty from faculty-search page
JNU uses: [at] and [dot] obfuscated emails embedded in <li> elements
"""
import requests
import re
import json

BASE = 'http://www.jnu.ac.in'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

url = f'{BASE}/faculty-search'
r = requests.get(url, timeout=(10, 20), headers=headers)

all_professors = []
all_emails = set()
all_phones = set()

# Parse each <li> entry containing [at]
entries = re.findall(r'<li>(.*?)</li>', r.text, re.DOTALL)

for entry in entries:
    if '[at]' not in entry.lower():
        continue
    
    # Extract name - look for name field
    name_match = re.search(r'>([^<]{3,80})</div>.*?\[at\]', entry)
    name = name_match.group(1).strip() if name_match else ''
    # Clean up extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Extract school/centre
    school_match = re.search(r'search-center-school[^>]*>([^<]+)', entry)
    school = school_match.group(1).strip() if school_match else ''
    
    # Extract emails - decode [at] -> @ and [dot] -> .
    raw_emails = re.findall(r'([a-zA-Z0-9._%+-]+\[at\][a-zA-Z0-9.-]+(?:\[dot\][a-zA-Z]+)+)', entry)
    for raw_email in raw_emails:
        email = raw_email.replace('[at]', '@').replace('[dot]', '.')
        all_emails.add(email)
    
    # Extract phone if present
    phone_match = re.search(r'(\+?91[\s-]?)?[6-9]\d{9}', entry)
    phone = phone_match.group(0) if phone_match else ''
    # Filter ISBNs
    if phone and phone.startswith(('978', '979')):
        phone = ''
    
    if name and all_emails:
        all_professors.append({
            'name': name,
            'email': '; '.join(sorted(set(
                e.replace('[at]', '@').replace('[dot]', '.')
                for e in re.findall(r'([a-zA-Z0-9._%+-]+\[at\][a-zA-Z0-9.-]+(?:\[dot\][a-zA-Z]+)+)', entry)
            ))),
            'phone': '',
            'school': school
        })

# Deduplicate by name + email
seen = set()
deduped = []
for p in all_professors:
    key = f"{p['name']}:{p['email']}"
    if key not in seen:
        seen.add(key)
        deduped.append(p)

count_at = sum(1 for e in entries if '[at]' in e.lower())
print(f'Total entries with [at]: {count_at}')
print(f'Professors extracted: {len(deduped)}')
print(f'Unique emails decoded: {len(all_emails)}')

result = {
    'url': 'http://www.jnu.ac.in/',
    'professors': deduped,
    'all_emails': list(all_emails),
    'all_phones': [],
    'statistics': {
        'professors_with_email': len([p for p in deduped if p['email']]),
    }
}

with open('scraper_output/jnu.json', 'w') as f:
    json.dump(result, f, indent=2)

print('Saved to scraper_output/jnu.json')
print('First 5 professors:')
for p in deduped[:5]:
    print(f'  {p["name"][:40]:40s} | {p["email"][:40]} | {p["school"][:30]}')
