#!/usr/bin/env python3
"""Apply approved category changes from the final staging file to the Paprika database.

Reads category_staging_final.json and applies all add/remove operations in a
single Paprika kill/restart cycle.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import time
import uuid

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/"
    "72KVKW69K8.com.hindsightlabs.paprika.mac.v3/"
    "Data/Database/Paprika.sqlite"
)
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
STAGING_PATH = os.path.join(DATA_DIR, "category_staging_final.json")


def _new_sync_hash() -> str:
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest().upper()


def _kill_paprika():
    subprocess.run(["killall", "Paprika Recipe Manager 3"], stderr=subprocess.DEVNULL, check=False)
    time.sleep(0.8)


def _open_paprika():
    subprocess.run(["open", "-a", "Paprika Recipe Manager 3"], stderr=subprocess.DEVNULL, check=False)


def main():
    # Load staging file
    with open(STAGING_PATH) as f:
        staging = json.load(f)

    changes = staging["changes"]
    # Only process recipes that actually have changes
    changes_with_work = [c for c in changes if c.get("add") or c.get("remove")]

    print(f"Loaded {len(changes)} total recipes in staging")
    print(f"Recipes with changes: {len(changes_with_work)}")

    if not changes_with_work:
        print("No changes to apply.")
        return

    # Pre-flight: read category map
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    categories = conn.execute(
        "SELECT Z_PK, ZNAME FROM ZRECIPECATEGORY WHERE ZSTATUS IS NULL OR ZSTATUS != 'deleted'"
    ).fetchall()
    cat_name_to_id = {row["ZNAME"]: row["Z_PK"] for row in categories}

    # Verify all category names exist in the DB
    all_cat_names = set()
    for change in changes_with_work:
        all_cat_names.update(change.get("add", []))
        all_cat_names.update(change.get("remove", []))

    missing = all_cat_names - set(cat_name_to_id.keys())
    if missing:
        print(f"ERROR: Unknown categories: {missing}")
        print("Fix the staging file and re-run.")
        conn.close()
        return

    # Get existing associations
    assocs = conn.execute("SELECT Z_12RECIPES, Z_13CATEGORIES FROM Z_12CATEGORIES").fetchall()
    existing_assocs = set()
    for a in assocs:
        existing_assocs.add((a["Z_12RECIPES"], a["Z_13CATEGORIES"]))
    conn.close()

    # Apply changes
    print("\nKilling Paprika...")
    _kill_paprika()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    total_added = 0
    total_removed = 0
    total_skipped = 0
    affected_recipes = set()

    for change in changes_with_work:
        recipe_id = change["id"]

        for cat_name in change.get("add", []):
            cat_id = cat_name_to_id[cat_name]
            if (recipe_id, cat_id) in existing_assocs:
                total_skipped += 1
                continue
            cursor.execute(
                "INSERT INTO Z_12CATEGORIES (Z_12RECIPES, Z_13CATEGORIES) VALUES (?, ?)",
                (recipe_id, cat_id),
            )
            existing_assocs.add((recipe_id, cat_id))
            total_added += 1
            affected_recipes.add(recipe_id)

        for cat_name in change.get("remove", []):
            cat_id = cat_name_to_id[cat_name]
            if (recipe_id, cat_id) not in existing_assocs:
                total_skipped += 1
                continue
            cursor.execute(
                "DELETE FROM Z_12CATEGORIES WHERE Z_12RECIPES = ? AND Z_13CATEGORIES = ?",
                (recipe_id, cat_id),
            )
            existing_assocs.discard((recipe_id, cat_id))
            total_removed += 1
            affected_recipes.add(recipe_id)

    # Mark all affected recipes as modified for sync
    for recipe_id in affected_recipes:
        cursor.execute(
            """
            UPDATE ZRECIPE
            SET Z_OPT = Z_OPT + 1, ZISSYNCED = 0,
                ZSTATUS = 'modified', ZSYNCHASH = ?
            WHERE Z_PK = ? AND ZINTRASH = 0
            """,
            (_new_sync_hash(), recipe_id),
        )

    conn.commit()
    conn.close()

    _open_paprika()

    print(f"\n=== APPLIED ===")
    print(f"Recipes modified: {len(affected_recipes)}")
    print(f"Categories added: {total_added}")
    print(f"Categories removed: {total_removed}")
    print(f"Skipped (already existed or already absent): {total_skipped}")
    print("Done!")


if __name__ == "__main__":
    main()
