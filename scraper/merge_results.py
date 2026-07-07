"""
Clean and merge all scraper results into colleges.json
"""
import json, glob, re, os

# Load existing data
with open('public/data/colleges.json') as f:
    data = json.load(f)

colleges = data['colleges']

# University name -> state mapping
UNI_MAP = {
    'igdtuw':              ('IGDTUW', 'Delhi'),
    'iiit_delhi':          ('IIIT Delhi', 'Delhi'),
    'jamia_millia_islamia': ('Jamia Millia Islamia', 'Delhi'),
    'jnu':                 ('Jawaharlal Nehru University', 'Delhi'),
    'nsut':                ('Netaji Subhas University of Technology', 'Delhi'),
    'dtu':                 ('Delhi Technological University', 'Delhi'),
    'sau':                 ('South Asian University', 'Delhi'),
    'du':                  ('University of Delhi', 'Delhi'),
    'aud':                 ('Dr. B.R. Ambedkar University', 'Delhi'),
    'ggsipu':              ('Guru Gobind Singh Indraprastha Vishwavidyalaya', 'Delhi'),
    'nlu_delhi':           ('National Law University', 'Delhi'),
    'teri_sas':            ('TERI School of Advanced studies', 'Delhi'),
}

def is_real_professor(name):
    name_lower = name.lower().strip()
    # Remove entries that are clearly not professor names
    skip = [
        'academic affairs', 'academics affairs', 'assistant warden', 'student welfare',
        'examinations affairs', 'faculty affairs', 'information technology',
        'international affairs', 'small text', 'helpdesk email numbers',
        'workshop superintendent', 'tech admissions',
        'faculties departments centres facilities', 'since apr', 'since aug',
        'since de', 'since dec', 'since feb', 'since jan', 'since jul',
        'since jun', 'since june', 'since mar', 'since may', 'since nov',
        'since oct', 'since sep', 'room no', 'respective email',
        'junior administrative officer', 'executive engineer',
        'faculty coordinator', 'assistant professor', 'associate professor',
        'professor', 'director', 'dean', 'hod', 'chairperson',
        'california institute', 'sc bangalore', 'san diego',
        'indian institute', 'alumni convocation', 'archives tenders',
        'box portal', 'collaborations viksit', 'contract labour',
        'data internal', 'faqs balance', 'happiness help',
        'kashmere gate', 'madrasa road opposite',
        'placements facilities careers', 'portal anvenshan',
        'head of department', 'head of the department', 'head of dept',
    ]
    for s in skip:
        if s in name_lower:
            return False
    # Must have at least one capital letter followed by lowercase
    if not re.match(r'^[A-Z][a-z]', name):
        return False
    # Must be between 5 and 50 chars
    if len(name) < 5 or len(name) > 50:
        return False
    # Skip names with tabs or multiple spaces
    if '\t' in name or '  ' in name:
        return False
    return True

def clean_name(name):
    """Clean up truncated names from IGDTUW format."""
    name = name.strip()
    # Remove trailing tab-text
    if '\t' in name:
        name = name.split('\t')[0].strip()
    return name

# Process each scraper output file
scraper_dir = 'scraper_output'
total_profs_added = 0

for fpath in sorted(glob.glob(os.path.join(scraper_dir, '*.json'))):
    base = os.path.basename(fpath).replace('.json', '')
    if base not in UNI_MAP:
        print(f"  Skipping unknown: {base}")
        continue
    
    uni_name, state = UNI_MAP[base]
    
    with open(fpath) as f:
        result = json.load(f)
    
    professors = result.get('professors', [])
    all_emails = result.get('all_emails', [])
    all_phones = result.get('all_phones', [])
    
    # Clean professors
    clean_profs = []
    for p in professors:
        name = clean_name(p.get('name', ''))
        if not is_real_professor(name):
            continue
        clean_profs.append({
            'name': name,
            'email': p.get('email', ''),
            'phone': p.get('phone', '')
        })
    
    if not clean_profs:
        print(f"  {uni_name:25s} -> 0 professors (all filtered)")
        continue
    
    # Find or create the entry in colleges.json
    matched = None
    for c in colleges:
        if uni_name.lower() in c.get('name', '').lower() and c.get('state', '') == state:
            matched = c
            break
    
    if not matched:
        # Also try partial match
        for c in colleges:
            c_name = c.get('name', '').lower()
            if state in c.get('state', '') and (uni_name.lower().replace('_', ' ') in c_name or 
                c_name.startswith(uni_name.lower().replace('_', ' ')[:5])):
                matched = c
                break
    
    if matched:
        matched['professors'] = clean_profs
        # Update college-level contact if we have better data
        if not matched.get('phone_numbers') and all_phones:
            matched['phone_numbers'] = '; '.join(sorted(all_phones)[:3])
        # Deduplicate emails
        all_college_emails = set()
        for p in clean_profs:
            for e in p.get('email', '').split('; '):
                e = e.strip()
                if e and '@' in e:
                    all_college_emails.add(e)
        if all_college_emails:
            matched['emails'] = '; '.join(sorted(all_college_emails)[:20])
        print(f"  {uni_name:25s} -> UPDATED ({len(clean_profs)} profs, {len(all_college_emails)} emails)")
    else:
        # Create new entry
        new_entry = {
            'id': str(max(int(c.get('id', 0) or 0) for c in colleges) + 1),
            'state': state,
            'name': uni_name,
            'address_line1': '',
            'address_line2': '',
            'city': 'New Delhi',
            'district': '',
            'pin_code': '',
            'website': result.get('url', ''),
            'phone_numbers': '; '.join(sorted(all_phones)[:3]) if all_phones else '',
            'emails': '; '.join(sorted(set(
                e for p in clean_profs for e in p.get('email', '').split('; ') if e and '@' in e
            ))[:20]),
            'professors': clean_profs
        }
        colleges.append(new_entry)
        print(f"  {uni_name:25s} -> ADDED ({len(clean_profs)} profs)")
    
    total_profs_added += len(clean_profs)

# Save
with open('public/data/colleges.json', 'w') as f:
    json.dump({'colleges': colleges}, f, indent=2)

print(f"\n{'='*50}")
print(f"Total professors added/updated: {total_profs_added}")
print(f"Total colleges now: {len(colleges)}")
states = set(c.get('state', '') for c in colleges)
print(f"States: {len(states)}")
