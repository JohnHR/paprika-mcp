#!/usr/bin/env python3
"""Dump all Paprika recipes to JSON with metadata and detect duplicates."""

import json
import os
import sqlite3
from collections import defaultdict
from urllib.parse import urlparse, urlunparse

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/"
    "72KVKW69K8.com.hindsightlabs.paprika.mac.v3/"
    "Data/Database/Paprika.sqlite"
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def normalize_url(url: str) -> str:
    """Strip query params, fragments, and trailing slash for comparison."""
    if not url:
        return ""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def dump_all_recipes():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # Get all active recipes
    recipes_raw = conn.execute("""
        SELECT Z_PK, ZNAME, ZSOURCEURL, ZRATING, ZONFAVORITES,
               ZPREPTIME, ZCOOKTIME, ZTOTALTIME, ZSERVINGS,
               ZINGREDIENTS, ZNOTES
        FROM ZRECIPE
        WHERE ZINTRASH = 0
        ORDER BY ZNAME COLLATE NOCASE
    """).fetchall()

    # Get all categories (non-date-based)
    all_categories = conn.execute("""
        SELECT Z_PK, ZNAME FROM ZRECIPECATEGORY
        WHERE ZNAME NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*'
          AND ZNAME NOT LIKE 'zz%'
    """).fetchall()
    cat_map = {row["Z_PK"]: row["ZNAME"] for row in all_categories}

    # Get all recipe-category associations
    assocs = conn.execute("SELECT Z_12RECIPES, Z_13CATEGORIES FROM Z_12CATEGORIES").fetchall()
    recipe_cats = defaultdict(list)
    for a in assocs:
        cat_name = cat_map.get(a["Z_13CATEGORIES"])
        if cat_name:
            recipe_cats[a["Z_12RECIPES"]].append(cat_name)

    # Build recipe list
    recipes = []
    for r in recipes_raw:
        pk = r["Z_PK"]
        recipes.append({
            "id": pk,
            "name": r["ZNAME"],
            "source_url": r["ZSOURCEURL"] or "",
            "rating": r["ZRATING"] or 0,
            "on_favorites": bool(r["ZONFAVORITES"]),
            "prep_time": r["ZPREPTIME"] or "",
            "cook_time": r["ZCOOKTIME"] or "",
            "total_time": r["ZTOTALTIME"] or "",
            "servings": r["ZSERVINGS"] or "",
            "categories": sorted(recipe_cats.get(pk, [])),
            "ingredients": r["ZINGREDIENTS"] or "",
            "notes": r["ZNOTES"] or "",
        })

    conn.close()

    # Write full dump
    dump_path = os.path.join(OUTPUT_DIR, "recipes_dump.json")
    with open(dump_path, "w") as f:
        json.dump(recipes, f, indent=2)
    print(f"Dumped {len(recipes)} recipes to {dump_path}")

    return recipes


def detect_duplicates(recipes):
    """Find duplicates by exact name and by normalized URL."""

    # --- Exact name duplicates ---
    by_name = defaultdict(list)
    for r in recipes:
        by_name[r["name"].strip().lower()].append(r)
    name_dupes = {k: v for k, v in by_name.items() if len(v) > 1}

    # --- URL duplicates ---
    by_url = defaultdict(list)
    for r in recipes:
        norm = normalize_url(r["source_url"])
        if norm:
            by_url[norm].append(r)
    url_dupes = {k: v for k, v in by_url.items() if len(v) > 1}

    # --- Uncategorized recipes ---
    uncategorized = [r for r in recipes if not r["categories"]]

    # Build report
    report = {
        "total_recipes": len(recipes),
        "uncategorized_count": len(uncategorized),
        "name_duplicate_groups": len(name_dupes),
        "url_duplicate_groups": len(url_dupes),
        "name_duplicates": [],
        "url_duplicates": [],
        "uncategorized": [],
    }

    for name_key, group in sorted(name_dupes.items()):
        report["name_duplicates"].append({
            "name": group[0]["name"],
            "recipes": [
                {"id": r["id"], "url": r["source_url"], "categories": r["categories"], "rating": r["rating"]}
                for r in group
            ]
        })

    for url_key, group in sorted(url_dupes.items()):
        # Skip if already covered by name duplicates
        report["url_duplicates"].append({
            "url": url_key,
            "recipes": [
                {"id": r["id"], "name": r["name"], "categories": r["categories"], "rating": r["rating"]}
                for r in group
            ]
        })

    for r in uncategorized:
        report["uncategorized"].append({
            "id": r["id"],
            "name": r["name"],
            "url": r["source_url"],
            "rating": r["rating"],
        })

    report_path = os.path.join(OUTPUT_DIR, "duplicate_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Duplicate report written to {report_path}")

    # Print summary
    print(f"\n=== SUMMARY ===")
    print(f"Total recipes: {report['total_recipes']}")
    print(f"Uncategorized: {report['uncategorized_count']}")
    print(f"Name duplicate groups: {report['name_duplicate_groups']}")
    print(f"URL duplicate groups: {report['url_duplicate_groups']}")

    if name_dupes:
        print(f"\n--- Name Duplicates ---")
        for group in report["name_duplicates"]:
            print(f"  \"{group['name']}\" ({len(group['recipes'])} copies)")
            for r in group["recipes"]:
                print(f"    ID={r['id']} rating={r['rating']} cats={r['categories']} url={r['url'][:80]}")

    if url_dupes:
        print(f"\n--- URL Duplicates ---")
        for group in report["url_duplicates"]:
            print(f"  URL: {group['url'][:100]}")
            for r in group["recipes"]:
                print(f"    ID={r['id']} \"{r['name']}\" rating={r['rating']} cats={r['categories']}")

    return report


if __name__ == "__main__":
    recipes = dump_all_recipes()
    detect_duplicates(recipes)
