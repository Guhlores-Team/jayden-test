"""Compare the matcher's decisions with the known answers for the sample data."""
import csv
from collections import Counter, defaultdict

with open("data/answer_key.csv") as fh:
    key = {r["row"]: r for r in csv.DictReader(fh)}
got = defaultdict(list)
with open("output/match_results.csv") as fh:
    for r in csv.DictReader(fh):
        got[r["row"]].append(r)

table, wrong_removals, mistakes = Counter(), 0, []
for row, k in key.items():
    decision = got[row][0]["decision"]
    ids = [x.get("listing_id") for x in got[row]]
    correct = decision == k["expected"] and (not k["listing_id"] or k["listing_id"] in ids)
    if decision == "remove" and ids[0] != k["listing_id"]:
        wrong_removals += 1
    table[(k["case"], k["expected"], "correct" if correct else f"WRONG: {decision}")] += 1
    if not correct:
        mistakes.append((k, got[row][0]))

print(f"{'case':45} {'expected':10} result")
for (case, expected, result), n in sorted(table.items()):
    print(f"{case:45} {expected:10} {n:4} {result}")
total = len(key)
print(f"\n{total - len(mistakes)}/{total} handled correctly; wrong listings removed: {wrong_removals}")
for k, g in mistakes[:10]:
    print(k, g)
