#!/usr/bin/env python3
"""Verify that category changes in the staging file are correctly reflected in the post-apply dump.

For each recipe with non-empty add/remove:
  - Checks that 'add' categories are present in the post-apply dump
  - Checks that 'remove' categories are absent in the post-apply dump

Reports all discrepancies.
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
STAGING_PATH = os.path.join(DATA_DIR, "category_staging_final.json")
POST_APPLY_DUMP_PATH = os.path.join(DATA_DIR, "recipes_dump_post_apply.json")


def main():
    with open(STAGING_PATH) as f:
        staging = json.load(f)

    with open(POST_APPLY_DUMP_PATH) as f:
        dump = json.load(f)

    # Build lookup: recipe id -> set of current categories
    dump_cats = {r["id"]: set(r["categories"]) for r in dump}

    missing_adds = []     # category should be present but isn't
    lingering_removes = [] # category should be absent but still there

    changes_checked = 0
    for change in staging["changes"]:
        if not change.get("add") and not change.get("remove"):
            continue

        changes_checked += 1
        recipe_id = change["id"]
        recipe_name = change["name"]

        actual_cats = dump_cats.get(recipe_id)
        if actual_cats is None:
            print(f"WARNING: recipe ID {recipe_id} ({recipe_name!r}) not found in post-apply dump")
            continue

        for cat in change.get("add", []):
            if cat not in actual_cats:
                missing_adds.append((recipe_id, recipe_name, cat))

        for cat in change.get("remove", []):
            if cat in actual_cats:
                lingering_removes.append((recipe_id, recipe_name, cat))

    print(f"Recipes with changes checked: {changes_checked}")
    print(f"Missing adds (should be present, isn't): {len(missing_adds)}")
    print(f"Lingering removes (should be gone, still there): {len(lingering_removes)}")

    if missing_adds:
        print("\n--- MISSING ADDS ---")
        for recipe_id, recipe_name, cat in sorted(missing_adds, key=lambda x: x[2]):
            print(f"  [{recipe_id}] {recipe_name!r}  →  missing: {cat!r}")

    if lingering_removes:
        print("\n--- LINGERING REMOVES ---")
        for recipe_id, recipe_name, cat in sorted(lingering_removes, key=lambda x: x[2]):
            print(f"  [{recipe_id}] {recipe_name!r}  →  still has: {cat!r}")

    if not missing_adds and not lingering_removes:
        print("\n✅ All changes verified — DB matches staging file perfectly.")
    else:
        total_issues = len(missing_adds) + len(lingering_removes)
        print(f"\n❌ {total_issues} discrepancies found.")


if __name__ == "__main__":
    main()
