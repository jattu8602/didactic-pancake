"""
Classify all colleges into Tier 1-5 based on institution type and name patterns.
Updates MongoDB with a 'tier' field (1-5).

Tier definitions:
  1 = Private Universities, Autonomous, NAAC A+/A++, Premier (IIT/NIT/IIIT)
  2 = Autonomous Colleges
  3 = State Universities
  4 = Deemed Universities
  5 = Affiliated / Government Colleges

Usage: python3 scraper/classify_tiers.py
"""
import re
import json
from pymongo import MongoClient, UpdateOne

MONGO_URL = "mongodb+srv://anchal:anchal@anchal.hospij1.mongodb.net/dbcolleges?appName=anchal"

TIER1_KEYWORDS = [
    'indian institute of technology', 'iit ',
    'national institute of technology', 'nit ',
    'indian institute of information technology', 'iiit ',
    'indian institute of management', 'iim ',
    'all india institute of medical sciences', 'aiims',
    'bennett university', 'chandigarh university',
    'shiv nadar', 'ashoka university',
    'azim premji', 'plaksha',
    'jio institute', 'reva university',
    'pES university', 'pes university',
    'SRM institute', 'srm institute',
    'lpu ', 'lovely professional',
    'amity university', 'sharda university',
    'galgotias university', 'vIT ', 'vit university',
    'manipal academy', 'manipal institute',
    'symbiosis international', 'KIIT ',
    'icfai university', 'ICFAI ',
    'MIT-World Peace', 'mit wpu',
    'MIT ADT', 'bml munjal',
    'OP Jindal', 'o.p. jindal',
    'GD Goenka', 'g.d. goenka',
    'Jain university', 'allah university',
    'kalinga institute', 'kl university', 'kl deemed',
    'kLE academy', 'kle academy',
    'CMR university', 'presidency university',
    'dayananda sagar university',
    'm s ramaiah', 'ramaiah institute',
    'rv college of engineering', 'r v college',
    'bms college of engineering', 'bmsce',
    'pes institute of technology',
    'new horizon college of engineering',
    'nitte deemed', 'nitte university',
    'sathyabama', 'bharath university',
    'saveetha university', 'vellore institute',
    'amrita university', 'amrita vishwa',
    'private university',
    'private engineering',
    'autonomous college',
]

TIER2_KEYWORDS = [
    'autonomous',
]

TIER3_KEYWORDS = [
    'university',
    'tribal university',
    'central university',
    'state university',
    'agricultural university',
    'technical university',
    'sanskrit university',
    'open university',
    'law university',
    'ayurveda university',
    'yoga university',
    'sports university',
    'teacher training',
    'dental university',
    'health sciences',
    'medical university',
    'veterinary',
    'fishery',
]

TIER4_KEYWORDS = [
    'deemed',
    'deemed to be',
]

TIER5_KEYWORDS = [
    'government college', 'govt. college', 'govt college',
    'degree college', 'junior college',
    'affiliated college',
]

KNOWN_TIER1_NAMES = [
    'bennett university', 'chandigarh university', 'ashoka university',
    'shiv nadar university', 'plaksha university',
    'srm institute of science', 'srm university',
    'lovely professional university', 'lpu',
    'amity university', 'sharda university',
    'vit university', 'vellore institute of technology',
    'manipal academy of higher education', 'manipal institute of technology',
    'symbiosis international university', 'symbiosis institute',
    'kiit university', 'kalinga institute of industrial technology',
    'icfai university',
    'mit world peace university', 'mit-wpu',
    'jain university', 'allah university',
    'kl university', 'kl deemed to be university',
    'kle academy of higher education', 'kle university',
    'reva university', 'presidency university',
    'galgotias university',
    'bml munjal university', 'o.p. jindal global university',
    'op jindal university', 'gd goenka university',
    'cmr university', 'pes university',
    'sharda university', 'sathyabama institute',
    'bharath institute of higher education', 'saveetha institute',
    'amrita vishwa vidyapeetham', 'amrita university',
    'vellore institute of technology',
    'dayananda sagar university',
    'm s ramaiah institute of technology',
    'rv college of engineering', 'r v college of engineering',
    'bms college of engineering', 'bmsce',
    'new horizon college of engineering',
    'nitte deemed to be university', 'nitte university',
    'pes institute of technology',
]

KNOWN_TIER3_NAMES = [
    'tripura university', 'maharaja bir bikram university',
    'delhi university', 'university of delhi',
    'mumbai university', 'university of mumbai',
    'calcutta university', 'university of calcutta',
    'madras university', 'university of madras',
    'bangalore university', 'university of bangalore',
    'mysore university', 'university of mysore',
    'pune university', 'savitribai phule pune university',
    'osmania university', 'kakatiya university',
    'andra university', 'sri venkateswara university',
    'anna university', 'gujarat university',
    'rajasthan university', 'university of rajasthan',
    'lucknow university', 'university of lucknow',
    'banaras hindu university', 'bhu',
    'aligarh muslim university', 'amu',
    'jamia millia islamia', 'jmi',
    'jawaharlal nehru university', 'jnu',
    'hyderabad central university', 'university of hyderabad',
    'puducherry university', 'pondicherry university',
    'nagpur university', 'rashtrasant tukadoji maharaj nagpur university', 'rtm nagpur',
    'barkatullah university', 'rajiv gandhi proudyogiki vishwavidyalaya', 'rgpv',
    'mizoram university', 'gauhati university',
    'dibrugarh university', 'assam university',
    'tezpur university', 'north eastern hill university', 'neh',
    'panjab university', 'punjab university',
    'guru nanak dev university', 'gndu',
    'punjabi university', 'patiala',
    'kurukshetra university', 'mahatma dayanand university',
    'himachal pradesh university', 'hpu',
    'jammu university', 'university of jammu',
    'kashmir university', 'university of kashmir',
]

# Tier 1 institutional keywords
TIER1_INSTITUTIONAL = [
    'iit ', 'nit ', 'iiit ', 'iim ', 'aiims', 'nits',
    'national institute of technology',
    'indian institute of technology',
    'indian institute of information technology',
    'indian institute of management',
]

def classify_tier(name):
    name_lower = name.lower().strip()
    name_lower_clean = re.sub(r'[^a-z0-9 ]', ' ', name_lower)
    name_lower_clean = re.sub(r'\s+', ' ', name_lower_clean).strip()

    # Check institutional first
    for kw in TIER1_INSTITUTIONAL:
        if kw.strip() in name_lower_clean or kw.strip() == name_lower_clean[:len(kw.strip())]:
            return 1

    # Check known Tier 1
    for known in KNOWN_TIER1_NAMES:
        if known in name_lower_clean:
            return 1

    # Check Tier 1 keywords
    for kw in TIER1_KEYWORDS:
        if kw in name_lower_clean:
            return 1

    # Tier 4 (Deemed) - check before Tier 3
    for kw in TIER4_KEYWORDS:
        if kw in name_lower_clean:
            return 4

    # Known Tier 3
    for known in KNOWN_TIER3_NAMES:
        if known in name_lower_clean:
            return 3

    # Tier 3 (State Universities)
    for kw in TIER3_KEYWORDS:
        if kw in name_lower_clean:
            return 3

    # Tier 2 (Autonomous)
    for kw in TIER2_KEYWORDS:
        if kw in name_lower_clean:
            return 2

    # Tier 5 - default for everything else
    return 5


def main():
    client = MongoClient(MONGO_URL)
    db = client['dbcolleges']
    col = db['colleges']

    all_colleges = list(col.find({}))

    updates = []
    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for doc in all_colleges:
        name = doc.get('name', '')
        tier = classify_tier(name)
        updates.append(UpdateOne(
            {'_id': doc['_id']},
            {'$set': {'tier': tier}}
        ))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    if updates:
        result = col.bulk_write(updates)
        print(f"Updated {result.modified_count} documents")

    print(f"\nTier distribution:")
    for t in sorted(tier_counts.keys()):
        print(f"  Tier {t}: {tier_counts[t]} colleges")


if __name__ == '__main__':
    main()
