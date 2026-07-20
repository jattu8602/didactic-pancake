"""
Merge Tripura scraper output into colleges.json
"""
import json, os, re, sys

COLLEGE_MAP = {
    "The ICFAI University Tripura" : ("The ICFAI University", "Tripura"),
    "Tripura University" : ("Tripura University", "Tripura"),
    "Maharaja Bir Bikram University" : ("Maharaja Bir Bikram University", "Tripura"),
    "Mata Tripura Sundari Open University" : ("Mata Tripura Sundari Open University", "Tripura"),
    "National Law University Tripura" : ("National Law University Tripura", "Tripura"),
    "Techno India University Tripura" : ("Techno India University", "Tripura"),
    "The Aryavart International University" : ("The Aryavart International University", "Tripura"),
    "The Dhamma Dipa International Buddhist University" : ("The Dhamma Dipa International Buddhist University", "Tripura"),
}

# Also fix the ICFAI name - in DB it might be different
# Check what name "The ICFAI University" has in Tripura

OUTDIR = '/Users/jattu/Desktop/colleges-api-master/scraper/output'
DB_PATH = '/Users/jattu/Desktop/colleges-api-master/public/data/colleges.json'

with open(DB_PATH) as f:
    db = json.load(f)

def clean_name(n):
    n = re.sub(r'^(Dr\.?\s*|Prof\.?\s*|Mr\.?\s*|Ms\.?\s*|Mrs\.?\s*)', '', n).strip()
    n = re.sub(r'\s+', ' ', n)
    return n

def find_college(db, name, state=None):
    for i, c in enumerate(db['colleges']):
        name_match = c['name'].strip().lower() == name.strip().lower()
        if name_match and (state is None or c.get('state', '').lower() == state.lower()):
            return i, c
    # Try without state filter
    for i, c in enumerate(db['colleges']):
        if c['name'].strip().lower() == name.strip().lower():
            return i, c
    return None, None

stats = {}
for file_name in sorted(os.listdir(OUTDIR)):
    if not file_name.endswith('.json'):
        continue
    file_path = os.path.join(OUTDIR, file_name)
    with open(file_path) as f:
        data = json.load(f)

    scraped_name = data['university']
    mapped = COLLEGE_MAP.get(scraped_name, (scraped_name, None))
    mapped_name, mapped_state = mapped
    idx, college = find_college(db, mapped_name, mapped_state)

    if college is None:
        print(f"SKIP: '{scraped_name}' -> '{mapped_name}' (state={mapped_state}) not found in DB")
        continue

    print(f"\n=== {scraped_name} -> {mapped_name} ===")

    # Gather emails from professors + all_emails
    all_emails = set(data.get('all_emails', []))
    prof_emails = set()
    for p in data.get('professors', []):
        if p.get('email'):
            for e in p['email'].split('; '):
                prof_emails.add(e.strip())
    all_emails.update(prof_emails)

    # Gather phones
    all_phones = set(data.get('all_phones', []))
    for p in data.get('professors', []):
        if p.get('phone'):
            for ph in p['phone'].split('; '):
                all_phones.add(ph.strip())

    # Build professors list - merge existing + new
    existing_profs = {p.get('email', ''): p for p in college.get('professors') or []}
    new_profs = 0
    for p in data.get('professors', []):
        name = p.get('name', '')
        email = p.get('email', '')
        phone = p.get('phone', '')
        clean_name_val = clean_name(name)

        if email and email in existing_profs:
            existing = existing_profs[email]
            if phone and not existing.get('phone'):
                existing['phone'] = phone
            if name and not existing.get('name'):
                existing['name'] = clean_name_val
        else:
            key = email if email else clean_name_val
            if key and key not in existing_profs:
                new_profs += 1
                existing_profs[key] = {
                    'name': clean_name_val,
                    'email': email,
                    'phone': phone
                }

    # Update college
    college['emails'] = '; '.join(sorted(all_emails)) if all_emails else ''
    college['phone_numbers'] = '; '.join(sorted(all_phones)) if all_phones else ''
    college['professors'] = list(existing_profs.values())
    college['tier'] = college.get('tier', 0)

    # Set tier based on data richness
    if len(college['professors']) > 5 or len(college['emails']) > 5:
        college['tier'] = 1
    elif len(college['professors']) >= 2 or len(college['emails']) >= 2:
        college['tier'] = min(college.get('tier', 3), 2)
    elif len(college['professors']) >= 1 or len(college['emails']) >= 1:
        college['tier'] = min(college.get('tier', 3), 2)

    college['websites'] = [data.get('url', '')]
    # Extract domain
    from urllib.parse import urlparse
    domain = urlparse(data.get('url', '')).netloc
    if domain:
        college['domains'] = [domain]

    stats[mapped_name] = {
        'profs': len(college['professors']),
        'emails': len(college['emails']),
        'phones': len(college['phone_numbers']),
        'tier': college['tier'],
        'new': new_profs
    }
    print(f"  Professors: {len(college['professors'])} ({new_profs} new)")
    print(f"  Emails: {len(college['emails'])}")
    print(f"  Phones: {len(college['phone_numbers'])}")

# Save
with open(DB_PATH, 'w') as f:
    json.dump(db, f, indent=2)

print("\n" + "="*50)
print("SUMMARY")
print("="*50)
for name, s in sorted(stats.items()):
    print(f"{name:40s} | tier={s['tier']} | profs={s['profs']:>3} | emails={s['emails']:>3} | phones={s['phones']:>3}")
print("="*50)
print("Saved to colleges.json")
