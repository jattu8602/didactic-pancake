"""
DTU scraper - extracts faculty from all department pages
DTU uses: mailto links with real emails + [at][dot] obfuscated display text
"""
import requests
import re
import json
import time

BASE = 'https://dtu.ac.in'

departments = [
    'AppliedChemistry', 'AppliedMathematics', 'AppliedPhysics', 'BioTech',
    'CSE', 'Civil', 'DSM', 'EVRT', 'Electrical', 'Electronics',
    'Environment', 'GST', 'Humanities', 'InformationTechnology',
    'MCG', 'Mechanical', 'SE', 'ScienceofHappiness', 'SportsResearch',
    'VinodDhamCenter', 'ccdr', 'design', 'eastcampus', 'phyedu',
]

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
all_professors = []
all_emails = set()
all_phones = set()
visited = set()

for dept in departments:
    url = f'{BASE}/Web/Departments/{dept}/faculty_v2'
    try:
        r = requests.get(url, timeout=(5, 10), headers=headers)
        if r.status_code != 200:
            continue
        
        # Extract mailto links
        mailtos = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', r.text)
        if not mailtos:
            continue
        
        text = r.text
        for email in mailtos:
            all_emails.add(email)
            # Try to find name near the email
            # Look for patterns like: <b>Name</b>...Email:...
            idx = text.find(f'mailto:{email}')
            if idx > 0:
                # Look backward for a name tag
                chunk = text[max(0,idx-500):idx]
                # Try to find name in bold tags
                names = re.findall(r'<b[^>]*>([^<]{5,50})</b>', chunk)
                # Filter out non-name bold text
                real_names = []
                for n in names:
                    n_clean = n.strip()
                    n_lower = n_clean.lower()
                    if (n_lower not in ['email:', 'research interests:', 'specialization:', 
                                        'designation:', 'phone:', 'mobile:', 'experience:',
                                        'qualification:', 'research interest:', 'area of interest:',
                                        'areas of interest:', 'supervisor:', 'research area:',
                                        'academic qualification:', 'teaching experience:',
                                        'industrial experience:', 'research experience:'] 
                        and len(n_clean) > 4 and re.match(r'^[A-Z][a-zA-Z\s.]+$', n_clean)):
                        real_names.append(n_clean)
                
                name = real_names[0] if real_names else email.split('@')[0]
                
                # Try to find phone number near the email
                phone_chunk = text[max(0,idx-500):idx+100]
                phones = re.findall(r'(?<!\d)(\+?91[\s-]?)?[6-9]\d{9}(?!\d)', phone_chunk)
                # Filter ISBNs
                real_phones = [p for p in phones if not re.match(r'^(978|979)', p)]
                
                all_professors.append({
                    'name': name,
                    'email': email,
                    'phone': '; '.join(real_phones[:2]) if real_phones else ''
                })
        
        print(f'  {dept:25s} -> {len(mailtos):2d} emails')
        visited.add(dept)
    except Exception as e:
        print(f'  {dept:25s} -> ERROR {e}')

print(f'\nTotal departments with faculty: {len(visited)}')
print(f'Total professors extracted: {len(all_professors)}')
print(f'Total unique emails: {len(all_emails)}')

# Deduplicate professors by email
seen_emails = set()
deduped = []
for p in all_professors:
    if p['email'] not in seen_emails:
        seen_emails.add(p['email'])
        deduped.append(p)

print(f'After dedup: {len(deduped)} professors')

result = {
    'url': 'https://dtu.ac.in/',
    'professors': deduped,
    'all_emails': list(all_emails),
    'all_phones': list(all_phones),
    'statistics': {
        'professors_with_email': len([p for p in deduped if p['email']]),
        'professors_with_phone': len([p for p in deduped if p['phone']]),
    }
}

with open('scraper_output/dtu.json', 'w') as f:
    json.dump(result, f, indent=2)

print(f'Saved to scraper_output/dtu.json')
