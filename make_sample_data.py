"""Generate a synthetic business directory and a removal list with known answers.

All businesses are invented. The removal list deliberately contains the messy cases
a real one has (different legal suffixes, typos, the same name in several cities,
companies that are not in the directory), and answer_key.csv records what the
correct outcome is for each row so the matcher's accuracy can be measured.
"""

import csv
import random
from pathlib import Path

SURNAMES = ["Abbott", "Alvarez", "Baker", "Barnes", "Bennett", "Brooks", "Carter", "Castillo", "Chen", "Coleman", "Cruz", "Dawson", "Delgado", "Ellis", "Fischer", "Foster", "Garcia", "Gibson", "Grant", "Hale", "Hayes", "Holt", "Ibarra", "Jensen", "Keller", "Kim", "Lambert", "Lopez", "Marsh", "Mendez", "Morgan", "Nash", "Novak", "Ortiz", "Park", "Patel", "Quinn", "Ramirez", "Reyes", "Rhodes", "Santos", "Shah", "Sloan", "Tanaka", "Torres", "Vance", "Vargas", "Walsh", "Webb", "Whitaker", "Yoder", "Zamora"]
ADJECTIVES = [
    "Summit",
    "Lone Star",
    "Blue Ridge",
    "Golden",
    "Premier",
    "Heritage",
    "Coastal",
    "Red Oak",
    "Silver Line",
    "Bright",
    "Evergreen",
    "Iron Gate",
    "Pioneer",
    "Liberty",
    "Crescent",
    "Northside",
    "Riverbend",
    "Cedar Park",
    "Granite",
    "Lakeside",
    "Metro",
    "Frontier",
    "Harbor",
    "Canyon",
    "Sunrise",
    "Keystone",
    "Capital",
    "Midtown",
    "Prairie",
    "Bluebonnet",
]
OUTSIDERS = [
    "Zenith", "Orchid", "Juniper", "Atlas", "Mosaic", "Quill", "Falcon", "Tundra", "Velvet", "Onyx",
    "Jubilee", "Kestrel", "Wexford", "Pinnacle", "Umbra", "Driftwood", "Sequoia", "Halcyon",
]
TRADES = {
    "Roofing": "Home Services",
    "Plumbing": "Home Services",
    "Electric": "Home Services",
    "Heating & Air": "Home Services",
    "Landscaping": "Home Services",
    "Pest Control": "Home Services",
    "Dental Care": "Health",
    "Family Clinic": "Health",
    "Physical Therapy": "Health",
    "Pharmacy": "Health",
    "Auto Repair": "Automotive",
    "Tire & Lube": "Automotive",
    "Collision Center": "Automotive",
    "Accounting": "Professional",
    "Law Group": "Professional",
    "Insurance Agency": "Professional",
    "Realty": "Professional",
    "Consulting": "Professional",
    "Bakery": "Food",
    "Coffee Roasters": "Food",
    "Catering": "Food",
    "Grill": "Food",
    "Fitness": "Lifestyle",
    "Pet Grooming": "Lifestyle",
    "Photography": "Lifestyle",
    "Cleaners": "Lifestyle",
    "Printing": "Business Services",
    "Logistics": "Business Services",
    "IT Solutions": "Business Services",
    "Staffing": "Business Services",
}
SUFFIXES = ["LLC", "Inc.", "Co.", "Ltd.", "Corp.", "& Sons", "Group", ""]
CITIES = [
    "Austin",
    "Dallas",
    "Houston",
    "San Antonio",
    "Fort Worth",
    "El Paso",
    "Plano",
    "Lubbock",
    "Corpus Christi",
    "Arlington",
    "Waco",
    "Round Rock",
]
STREETS = [
    "Main St",
    "Oak Ave",
    "Congress Ave",
    "Elm St",
    "Commerce St",
    "Lamar Blvd",
    "Market St",
    "Pecan Dr",
    "Mesa Rd",
    "Ranch Rd",
    "Bluff Ln",
    "Cypress Way",
]
SUFFIX_SWAPS = {
    "LLC": ["L.L.C.", "Limited Liability Company", ""],
    "Inc.": ["Incorporated", "Inc", "INC"],
    "Co.": ["Company", "Co"],
    "Ltd.": ["Limited", "LTD"],
    "Corp.": ["Corporation", "Corp"],
}


def typo(rng, name):
    """Drop a letter or swap two neighbours, as a hurried typist would."""
    letters = [i for i, ch in enumerate(name) if ch.isalpha()]
    while True:
        i = rng.choice(letters[2:-1])
        if rng.random() < 0.5:
            changed = name[:i] + name[i + 1 :]
        else:
            changed = name[:i] + name[i + 1] + name[i] + name[i + 2 :]
        if changed != name:
            return changed


def reformat(rng, base, suffix):
    choice = rng.choice(["suffix", "ampersand", "case", "punctuation", "the"])
    name = f"{base} {suffix}".strip()
    if choice == "suffix" and suffix in SUFFIX_SWAPS:
        return f"{base} {rng.choice(SUFFIX_SWAPS[suffix])}".strip()
    if choice == "ampersand" and "&" in name:
        return name.replace("&", "and")
    if choice == "case":
        return name.upper()
    if choice == "punctuation":
        return name.replace(".", "").replace(" LLC", ", LLC")
    return f"The {name}"


def main(out="data", size=5000, seed=7):
    rng = random.Random(seed)
    out = Path(out)
    out.mkdir(exist_ok=True)
    trades = list(TRADES)

    bases = set()
    while len(bases) < size - 150:
        roll = rng.random()
        if roll < 0.4:
            lead = rng.choice(SURNAMES)
        elif roll < 0.6:
            lead = rng.choice(ADJECTIVES)
        else:
            lead = " & ".join(rng.sample(SURNAMES, 2))
        bases.add(f"{lead} {rng.choice(trades)}")
    bases = sorted(bases)
    rng.shuffle(bases)

    listings = []

    def add(base, suffix, city):
        trade = next(t for t in trades if base.endswith(t))
        listings.append(
            {
                "listing_id": f"L{len(listings) + 1:05d}",
                "base": base,
                "suffix": suffix,
                "company_name": f"{base} {suffix}".strip(),
                "category": TRADES[trade],
                "address": f"{rng.randint(100, 9999)} {rng.choice(STREETS)}",
                "city": city,
                "state": "TX",
                "phone": f"({rng.choice([512, 214, 713, 210, 817, 915])}) 555-{rng.randint(0, 9999):04d}",
            }
        )
        return listings[-1]

    multi = []
    for base in bases:
        suffix = rng.choice(SUFFIXES)
        first = add(base, suffix, rng.choice(CITIES))
        if len(listings) < size and len(multi) < 150:
            other = add(
                base, suffix, rng.choice([c for c in CITIES if c != first["city"]])
            )
            multi.append((first, other))
    rng.shuffle(listings)

    multi_ids = {x["listing_id"] for pair in multi for x in pair}
    singles = [x for x in listings if x["listing_id"] not in multi_ids]
    rng.shuffle(singles)
    take = iter(singles)

    requests, answers = [], []

    def ask(name, city, expected, case, listing_id=""):
        requests.append({"row": len(requests) + 1, "company_name": name, "city": city})
        answers.append(
            {
                "row": len(requests),
                "case": case,
                "expected": expected,
                "listing_id": listing_id,
            }
        )

    for _ in range(300):
        x = next(take)
        ask(
            x["company_name"],
            x["city"] if rng.random() < 0.7 else "",
            "remove",
            "exact name",
            x["listing_id"],
        )
    for _ in range(120):
        x = next(take)
        ask(
            reformat(rng, x["base"], x["suffix"]),
            x["city"],
            "remove",
            "different formatting",
            x["listing_id"],
        )
    for _ in range(60):
        x = next(take)
        ask(
            typo(rng, x["company_name"]),
            x["city"],
            "review",
            "typo in name",
            x["listing_id"],
        )
    for first, _ in multi[:40]:
        ask(
            first["company_name"],
            first["city"],
            "remove",
            "same name in two cities, city given",
            first["listing_id"],
        )
    for first, _ in multi[40:70]:
        ask(
            first["company_name"],
            "",
            "review",
            "same name in two cities, no city given",
        )
    for _ in range(25):
        x = next(take)
        wrong_city = rng.choice([c for c in CITIES if c != x["city"]])
        ask(x["company_name"], wrong_city, "review", "name matches but city differs")
    existing = {x["base"] for x in listings}
    made = 0
    while made < 25:
        base = f"{rng.choice(OUTSIDERS)} {rng.choice(trades)}"
        if base not in existing:
            ask(
                f"{base} {rng.choice(SUFFIXES)}".strip(),
                rng.choice(CITIES),
                "not found",
                "not in the directory",
            )
            made += 1

    order = list(range(len(requests)))
    rng.shuffle(order)
    requests = [dict(requests[i], row=n + 1) for n, i in enumerate(order)]
    answers = [dict(answers[i], row=n + 1) for n, i in enumerate(order)]

    fields = [
        "listing_id",
        "company_name",
        "category",
        "address",
        "city",
        "state",
        "phone",
    ]
    for name, rows, cols in (
        ("directory.csv", listings, fields),
        ("removal_list.csv", requests, ["row", "company_name", "city"]),
        ("answer_key.csv", answers, ["row", "case", "expected", "listing_id"]),
    ):
        with open(out / name, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    print(
        f"{len(listings)} listings, {len(requests)} removal requests written to {out}/"
    )


if __name__ == "__main__":
    main()
