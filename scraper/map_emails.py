import json

with open("sbu_clean.json") as f:
    data = json.load(f)

# ── 1. Use ONLY verified mappings from individual faculty-profile pages ──
known = {}
for page in data["pages"]:
    if "faculty-profile/SBU-" in page["url"] and "?" not in page["url"]:
        faculty_emails = [
            e for e in page["emails"] if e not in (
                "admissions@sbu.ac.in", "vc@sbu.ac.in",
            )
        ]
        for prof in page["profs"]:
            name = prof.split("\n")[0].split("\t")[0].strip()
            if name in ("Ms Objective", "Dr. Manoj Pandey Remember", "Dr. Bandi"):
                continue
            for email in faculty_emails:
                known.setdefault(name, [])
                if email not in known[name]:
                    known[name].append(email)

# ── 2. Role emails ──
ROLE_EMAILS = {
    "admissions@sbu.ac.in": "Admissions Office",
    "vc@sbu.ac.in": "Vice Chancellor",
    "dg@sbu.ac.in": "Director General",
    "sb.dandin@sbu.ac.in": "Registrar / Controller of Examinations",
    "library@sbu.ac.in": "Library",
    "dsw@sbu.ac.in": "Dean Student Welfare",
    "examination@sbu.ac.in": "Examination Department",
    "internationaloffice@sbu.ac.in": "International Office",
    "careerservices@sbu.ac.in": "Career Services",
}

# ── 3. Collect all faculty emails from /faculties page ──
faculties_page = None
for page in data["pages"]:
    if page["url"] == "https://sbu.ac.in/faculties" and "?" not in page["url"]:
        faculties_page = page
        break

all_faculty_emails = sorted(set(
    e for e in faculties_page["emails"]
    if e not in ROLE_EMAILS
)) if faculties_page else []

# ── 4. Build verified mapping ──
verified = {}  # email -> prof_name
for name, emails in known.items():
    for e in emails:
        verified[e] = name

# ── 5. Separate matched and unmatched ──
matched = []
unmatched = []
for e in all_faculty_emails:
    if e in verified:
        matched.append((e, verified[e]))
    else:
        unmatched.append(e)

# ── 6. Build output ──
output = {
    "faculty_email_map": [],
    "role_emails": [],
}

for email, dept in sorted(ROLE_EMAILS.items()):
    output["role_emails"].append({"email": email, "department": dept})

for email, prof in sorted(matched, key=lambda x: x[1]):
    output["faculty_email_map"].append({"professor": prof, "email": email})

for email in sorted(unmatched):
    output["faculty_email_map"].append({
        "professor": "⚠ UNMATCHED (not on individual profile page)",
        "email": email,
    })

# ── 7. Print ──
print("=" * 70)
print(f"EMAIL → PROFESSOR MAPPING ({len(matched)} verified, {len(unmatched)} unmatched)")
print("=" * 70)
print()
for item in output["faculty_email_map"]:
    tag = "✓" if not item["professor"].startswith("⚠") else "⚠"
    print(f"  {tag} {item['email']:40s} → {item['professor']}")

print(f"\n── Role Emails ({len(output['role_emails'])}) ──")
for item in output["role_emails"]:
    print(f"  {item['email']:40s} → {item['department']}")

with open("sbu_email_map.json", "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to sbu_email_map.json")
