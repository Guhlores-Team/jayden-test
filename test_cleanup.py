import csv

import pytest

import cleanup
from cleanup import Directory, classify, normalize

LISTINGS = [
    {"listing_id": "L1", "company_name": "Summit Roofing LLC", "city": "Austin"},
    {"listing_id": "L2", "company_name": "Baker & Sons Plumbing Inc.", "city": "Dallas"},
    {"listing_id": "L3", "company_name": "Harbor Dental Care", "city": "Houston"},
    {"listing_id": "L4", "company_name": "Harbor Dental Care", "city": "Waco"},
    {"listing_id": "L5", "company_name": "Ibarra Physical Therapy Co.", "city": "Plano"},
]


@pytest.fixture
def directory():
    return Directory([dict(r) for r in LISTINGS])


@pytest.mark.parametrize(
    "a, b",
    [
        ("Summit Roofing LLC", "SUMMIT ROOFING, L.L.C."),
        ("Baker & Sons Plumbing Inc.", "Baker and Sons Plumbing Incorporated"),
        ("The Harbor Dental Care Company", "Harbor Dental Care"),
        ("Café Río Ltd", "Cafe Rio Limited"),
    ],
)
def test_normalize_ignores_formatting(a, b):
    assert normalize(a) == normalize(b)


def test_normalize_keeps_different_companies_apart():
    assert normalize("Summit Roofing") != normalize("Summit Plumbing")


def decision(directory, name, city=""):
    result, _, candidates = classify(directory, name, city)
    return result, [directory.rows[i]["listing_id"] for _, i in candidates]


def test_exact_match_with_city_is_removed(directory):
    assert decision(directory, "summit roofing", "Austin") == ("remove", ["L1"])


def test_unique_name_without_city_is_removed(directory):
    assert decision(directory, "Baker and Sons Plumbing") == ("remove", ["L2"])


def test_city_picks_between_same_named_listings(directory):
    assert decision(directory, "Harbor Dental Care", "Waco") == ("remove", ["L4"])


def test_same_name_without_city_needs_review(directory):
    result, ids = decision(directory, "Harbor Dental Care")
    assert result == "review" and sorted(ids) == ["L3", "L4"]


def test_wrong_city_needs_review(directory):
    assert decision(directory, "Summit Roofing LLC", "El Paso") == ("review", ["L1"])


def test_typo_needs_review_not_removal(directory):
    assert decision(directory, "Sumit Roofing LLC", "Austin") == ("review", ["L1"])
    assert decision(directory, "Ibrara Physical Therapy", "Plano") == ("review", ["L5"])


def test_lookalike_company_is_not_matched(directory):
    assert decision(directory, "Umbra Physical Therapy Corp.", "Plano") == ("not found", [])


def test_unknown_company_is_not_found(directory):
    assert decision(directory, "Zenith Bakery") == ("not found", [])


def write(path, rows):
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_apply_removes_only_confirmed_and_keeps_backup(tmp_path):
    write(tmp_path / "directory.csv", LISTINGS)
    write(
        tmp_path / "removals.csv",
        [
            {"company_name": "Summit Roofing", "city": "Austin"},
            {"company_name": "SUMMIT ROOFING LLC", "city": ""},
            {"company_name": "Harbor Dental Care", "city": ""},
            {"company_name": "Zenith Bakery", "city": ""},
        ],
    )
    out = tmp_path / "out"
    args = ["--directory", str(tmp_path / "directory.csv"), "--removals", str(tmp_path / "removals.csv"), "--out", str(out)]

    cleanup.main(args)
    assert not (out / "directory_cleaned.csv").exists(), "a dry run must not write a cleaned directory"

    results = cleanup.main(args + ["--apply"])
    assert [r["decision"] for r in results] == ["remove", "duplicate", "review", "not found"]
    kept = [r["listing_id"] for r in cleanup.read_csv(out / "directory_cleaned.csv")]
    assert kept == ["L2", "L3", "L4", "L5"]
    assert [r["listing_id"] for r in cleanup.read_csv(out / "removal_log.csv")] == ["L1"]
    backups = list((out / "backup").glob("*.csv"))
    assert len(backups) == 1 and len(cleanup.read_csv(backups[0])) == len(LISTINGS)


def test_client_approval_releases_a_review_item(tmp_path):
    write(tmp_path / "directory.csv", LISTINGS)
    write(tmp_path / "removals.csv", [{"company_name": "Harbor Dental Care", "city": ""}])
    write(tmp_path / "approvals.csv", [{"row": 1, "listing_id": "L3"}])
    out = tmp_path / "out"
    cleanup.main(
        ["--directory", str(tmp_path / "directory.csv"), "--removals", str(tmp_path / "removals.csv"),
         "--approvals", str(tmp_path / "approvals.csv"), "--out", str(out), "--apply"]
    )
    assert [r["listing_id"] for r in cleanup.read_csv(out / "directory_cleaned.csv")] == ["L1", "L2", "L4", "L5"]
