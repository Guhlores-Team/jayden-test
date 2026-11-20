"""Remove businesses from a directory based on a list of company names.

Each requested name is matched against the directory and placed in one of three groups:
  remove     the name matches exactly once formatting is ignored, and the city agrees
             (or no city was given and only one listing has that name)
  review     a close but not certain match: a likely typo, several listings with the
             same name, or a city that disagrees. Never removed without sign-off.
  not found  nothing in the directory is similar enough

Nothing is deleted unless --apply is passed, and the original file is backed up first.
"""

import argparse
import csv
import re
import shutil
import time
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

LEGAL_WORDS = {
    "llc",
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "co",
    "company",
    "corp",
    "corporation",
    "plc",
    "lp",
    "llp",
    "pllc",
    "gmbh",
    "liability",
}
REVIEW_THRESHOLD = 0.85
WORD_THRESHOLD = 0.7


def normalize(name):
    """Reduce a company name to the part that identifies it."""
    text = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    text = text.replace("&", " and ")
    text = re.sub(r"(?<=\b[a-z])\.(?=[a-z]\b)", "", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    words = [w for w in text.split() if w not in LEGAL_WORDS]
    if words and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def same_city(a, b):
    return normalize(a) == normalize(b)


def distinct_words_agree(a, b):
    """Guard against names that only look alike because they share a long generic part.

    "Umbra Physical Therapy" and "Ibarra Physical Therapy" are 89% similar as strings,
    but the words that differ are unrelated, so they are different companies.
    """
    words_a, words_b = a.split(), b.split()
    only_a = [w for w in words_a if w not in words_b]
    only_b = [w for w in words_b if w not in words_a]
    if not only_a or not only_b:
        return True
    left, right = " ".join(only_a), " ".join(only_b)
    # difflib scores swapped neighbouring letters ("iar" for "air") poorly, so accept same-letter words too.
    return sorted(left) == sorted(right) or SequenceMatcher(None, left, right).ratio() >= WORD_THRESHOLD


class Directory:
    def __init__(self, rows, name_col="company_name"):
        self.rows = rows
        self.by_name = defaultdict(list)
        self.by_word = defaultdict(set)
        self.keys = []
        for i, row in enumerate(rows):
            key = normalize(row[name_col])
            self.keys.append(key)
            self.by_name[key].append(i)
            for word in key.split():
                self.by_word[word].add(i)

    def similar(self, key, limit=3):
        """Closest listings that share at least one word with the requested name."""
        candidates = set()
        for word in key.split():
            candidates |= self.by_word.get(word, set())
        scored = []
        for i in candidates:
            matcher = SequenceMatcher(None, key, self.keys[i])
            if matcher.quick_ratio() < REVIEW_THRESHOLD:
                continue
            score = matcher.ratio()
            if score >= REVIEW_THRESHOLD and distinct_words_agree(key, self.keys[i]):
                scored.append((score, i))
        return sorted(scored, reverse=True)[:limit]


def classify(directory, name, city):
    """Returns (decision, reason, [(score, row_index), ...])."""
    key = normalize(name)
    if not key:
        return "not found", "The requested name is empty", []
    exact = directory.by_name.get(key, [])
    if exact:
        if city:
            in_city = [i for i in exact if same_city(directory.rows[i]["city"], city)]
            if len(in_city) == 1:
                return "remove", "Name and city match", [(1.0, in_city[0])]
            if len(in_city) > 1:
                return (
                    "review",
                    "Several listings share this name and city",
                    [(1.0, i) for i in in_city],
                )
            return (
                "review",
                "Name matches, but the listing is in a different city",
                [(1.0, i) for i in exact],
            )
        if len(exact) == 1:
            return "remove", "Name matches exactly one listing", [(1.0, exact[0])]
        return (
            "review",
            "Several listings share this name and no city was given",
            [(1.0, i) for i in exact],
        )
    close = directory.similar(key)
    if close:
        return "review", "Similar name found (possible typo)", close
    return "not found", "No similar listing in the directory", []


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def match_all(directory, requests):
    results = []
    for n, req in enumerate(requests, start=1):
        decision, reason, candidates = classify(
            directory, req.get("company_name", ""), req.get("city", "")
        )
        results.append(
            {
                "row": req.get("row") or n,
                "requested_name": req.get("company_name", ""),
                "requested_city": req.get("city", ""),
                "decision": decision,
                "reason": reason,
                "candidates": candidates,
            }
        )
    # Two requests pointing at the same listing is a duplicate in the client's list; keep the first.
    seen = {}
    for res in results:
        if res["decision"] == "remove":
            idx = res["candidates"][0][1]
            if idx in seen:
                res["decision"], res["reason"] = (
                    "duplicate",
                    f"Same listing as request row {seen[idx]}",
                )
            else:
                seen[idx] = res["row"]
    return results


def apply_approvals(directory, results, approvals):
    """approvals: rows of {row, listing_id} signed off by the client for 'review' items."""
    by_id = {r["listing_id"]: i for i, r in enumerate(directory.rows)}
    by_row = {str(r["row"]): r for r in results}
    removing = {r["candidates"][0][1] for r in results if r["decision"] == "remove"}
    for approval in approvals:
        res, idx = by_row.get(str(approval["row"])), by_id.get(approval["listing_id"])
        if res is None or idx is None or res["decision"] != "review":
            raise ValueError(f"Approval does not match a review item: {approval}")
        if idx not in {i for _, i in res["candidates"]}:
            raise ValueError(
                f"Approved listing was not a suggested candidate: {approval}"
            )
        if idx in removing:
            res["decision"], res["reason"] = (
                "duplicate",
                "Approved listing is already being removed",
            )
            continue
        removing.add(idx)
        res["decision"], res["reason"], res["candidates"] = (
            "remove",
            "Approved by client after review",
            [(1.0, idx)],
        )


def flatten(directory, res):
    """One output row per candidate listing (or one row with no listing)."""
    base = {
        k: res[k]
        for k in ("row", "requested_name", "requested_city", "decision", "reason")
    }
    if not res["candidates"]:
        return [base]
    out = []
    for score, idx in res["candidates"]:
        listing = directory.rows[idx]
        out.append(
            {
                **base,
                "similarity": round(score, 3),
                "listing_id": listing["listing_id"],
                "listing_name": listing["company_name"],
                "listing_city": listing["city"],
                "listing_address": listing.get("address", ""),
                "listing_phone": listing.get("phone", ""),
            }
        )
    return out


REPORT_FIELDS = [
    "row",
    "requested_name",
    "requested_city",
    "decision",
    "reason",
    "similarity",
    "listing_id",
    "listing_name",
    "listing_city",
    "listing_address",
    "listing_phone",
]


def write_report(path, directory, results, applied):
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    counts = defaultdict(int)
    for res in results:
        counts[res["decision"]] += 1
    removed = counts["remove"]
    rows = [
        ("Listings in directory before", len(directory.rows)),
        ("Removal requests received", len(results)),
        ("Removed" if applied else "Ready to remove", removed),
        ("Needs your review (not removed)", counts["review"]),
        ("Not found in directory", counts["not found"]),
        ("Duplicate requests (same listing asked twice)", counts["duplicate"]),
        (
            "Listings in directory after",
            len(directory.rows) - removed if applied else "unchanged (dry run)",
        ),
    ]
    summary.append(["Directory removal report"])
    summary["A1"].font = Font(bold=True, size=14)
    summary.append([])
    for label, value in rows:
        summary.append([label, value])
    summary.column_dimensions["A"].width = 48
    summary.column_dimensions["B"].width = 22

    header_fill = PatternFill("solid", fgColor="1F3864")
    sheets = (
        ("Removed" if applied else "To remove", "remove"),
        ("Needs review", "review"),
        ("Not found", "not found"),
        ("Duplicates", "duplicate"),
    )
    for title, decision in sheets:
        ws = wb.create_sheet(title)
        fields = REPORT_FIELDS + (["approve? (yes/no)"] if decision == "review" else [])
        ws.append(fields)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
        for res in results:
            if res["decision"] == decision:
                for flat in flatten(directory, res):
                    ws.append([flat.get(f, "") for f in fields])
        ws.freeze_panes = "A2"
        for col, width in zip(
            "ABCDEFGHIJKL", (6, 34, 16, 11, 46, 10, 10, 34, 16, 24, 16, 18)
        ):
            ws.column_dimensions[col].width = width
    wb.save(path)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--directory",
        required=True,
        help="CSV with listing_id, company_name, city, ...",
    )
    ap.add_argument(
        "--removals", required=True, help="CSV with company_name and optional city"
    )
    ap.add_argument(
        "--approvals",
        help="CSV with row, listing_id for review items the client approved",
    )
    ap.add_argument("--out", default="output")
    ap.add_argument(
        "--apply", action="store_true", help="actually remove the confirmed listings"
    )
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = read_csv(args.directory)
    directory = Directory(rows)
    results = match_all(directory, read_csv(args.removals))
    if args.approvals:
        apply_approvals(directory, results, read_csv(args.approvals))

    flat = [f for res in results for f in flatten(directory, res)]
    write_csv(out / "match_results.csv", flat, REPORT_FIELDS)

    if args.apply:
        backup_dir = out / "backup"
        backup_dir.mkdir(exist_ok=True)
        backup = (
            backup_dir
            / f"{Path(args.directory).stem}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        )
        shutil.copy2(args.directory, backup)
        removing = {
            res["candidates"][0][1] for res in results if res["decision"] == "remove"
        }
        kept = [row for i, row in enumerate(rows) if i not in removing]
        write_csv(out / "directory_cleaned.csv", kept, list(rows[0].keys()))
        log = [
            {**rows[i], "removed_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            for i in sorted(removing)
        ]
        write_csv(out / "removal_log.csv", log, list(rows[0].keys()) + ["removed_at"])
        assert len(kept) + len(removing) == len(rows)
        print(f"Backup saved to {backup}")

    counts = write_report(out / "removal_report.xlsx", directory, results, args.apply)
    verb = "removed" if args.apply else "ready to remove (dry run)"
    print(
        f"{counts['remove']} {verb}, {counts['review']} need review, "
        f"{counts['not found']} not found, {counts['duplicate']} duplicate requests"
    )
    return results


if __name__ == "__main__":
    main()
