"""
Combine mp_colleges.csv + scraped district CSVs into public/data/colleges.json
Run this after scraping new districts to update the frontend.
"""
import csv, json, os

MP_CSV = "../data/mp_colleges.csv"
SCRAPED_DIR = "../data/scraped"
OUTPUT = "../public/data/colleges.json"

with open(MP_CSV, encoding="utf-8-sig") as f:
    base = list(csv.DictReader(f))

for r in base:
    r["id"] = r.pop("\ufeffid", r.get("id", ""))

by_id = {r["id"]: r for r in base}

if os.path.exists(SCRAPED_DIR):
    for fname in os.listdir(SCRAPED_DIR):
        if fname.endswith(".csv"):
            with open(os.path.join(SCRAPED_DIR, fname), encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    rid = row.get("id", "")
                    if rid in by_id:
                        by_id[rid]["website"] = row.get("website", "")
                        by_id[rid]["phone_numbers"] = row.get("phone_numbers", "")
                        by_id[rid]["emails"] = row.get("emails", "")

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w") as f:
    json.dump({"colleges": list(by_id.values())}, f)

total = len(by_id)
merged = sum(1 for r in by_id.values() if r.get("phone_numbers") or r.get("emails"))
print(f"Done: {total} colleges, {merged} with contact data → {OUTPUT}")
