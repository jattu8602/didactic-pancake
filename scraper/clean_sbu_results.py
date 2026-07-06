import json, re

with open("sbu_results.json") as f:
    data = json.load(f)

# These appear on nearly every page (footer) — strip per-page but keep globally
FOOTER_PHONES = {
    "+91 7479537160", "+91 7707004287", "+91 7707006064",
    "+91 9525110001", "+91 8789771545", "+91 7707006061",
    "18008906077", "+91 7707006065",
}

def is_real_phone(p: str) -> bool:
    s = p.strip()
    # Must look like a phone number pattern
    patterns = [
        r'^\+91[\s-]?\d{7,10}$',                # +91 format
        r'^0\d{2,4}[\s-]?\d{6,8}$',             # STD code format
        r'^1800[\s-]?\d{3}[\s-]?\d{4}$',         # Toll-free
        r'^[0789]\d{4}[\s-]\d{5}$',               # Mobile (5+5 with separator, Indian prefix)
        r'^\d{4}[\s-]\d{7}$',                     # Landline (4+7 with separator)
        r'^[789]\d{9}$',                          # 10-digit mobile starting with 7/8/9
    ]
    for pat in patterns:
        if re.match(pat, s):
            return True
    return False

real_phones = set()
real_emails = set()
all_profs = []

for page in data["pages"]:
    clean_phones = []
    for ph in page["phones"]:
        if ph in FOOTER_PHONES:
            continue
        if not is_real_phone(ph):
            continue
        clean_phones.append(ph)
        real_phones.add(ph)
    page["phones"] = clean_phones

# Add footer phones once to the global summary
real_phones.update(FOOTER_PHONES)

for page in data["pages"]:
    for e in page["emails"]:
        real_emails.add(e)
    for prof in page["profs"]:
        all_profs.append(prof)

# Deduplicate profs (first occurrence preserves page order)
seen_profs = set()
unique_profs = []
for p in all_profs:
    key = p.strip()
    if key not in seen_profs:
        seen_profs.add(key)
        unique_profs.append(p)

summary = {
    "total_phones": len(real_phones),
    "total_emails": len(real_emails),
    "total_profs": len(unique_profs),
    "phones": sorted(real_phones),
    "emails": sorted(real_emails),
    "profs": unique_profs,
}

output = {"pages": data["pages"], "summary": summary}

with open("sbu_clean.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"Cleaned data saved to scraper/sbu_clean.json")
print(f"\nSummary:")
print(f"  Pages: {len(data['pages'])}")
print(f"  Real phones: {len(real_phones)}")
print(f"  Emails: {len(real_emails)}")
print(f"  Staff/Profs: {len(unique_profs)}")
print(f"\nPhones:")
for ph in sorted(real_phones):
    print(f"  {ph}")
print(f"\nEmails:")
for e in sorted(real_emails):
    print(f"  {e}")
print(f"\nTop Profs:")
for p in unique_profs[:30]:
    print(f"  {p}")
if len(unique_profs) > 30:
    print(f"  ... and {len(unique_profs)-30} more")
