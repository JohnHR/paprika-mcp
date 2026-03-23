#!/usr/bin/env python3
"""Merge overlapping categories in the Paprika database.

Merges:
  1. AAA Easy/Quick (134) → Weekday (13), then delete AAA Easy/Quick
  2. AAA Up Next (8) → Try Soon (17), then delete AAA Up Next

For each merge: move all recipe associations from source to target
(skipping duplicates), then soft-delete the source category.
"""

import hashlib
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


def _new_sync_hash() -> str:
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest().upper()


def _kill_paprika():
    subprocess.run(["killall", "Paprika Recipe Manager 3"], stderr=subprocess.DEVNULL, check=False)
    time.sleep(0.8)


def _open_paprika():
    subprocess.run(["open", "-a", "Paprika Recipe Manager 3"], stderr=subprocess.DEVNULL, check=False)


def merge_category(cursor, source_id, source_name, target_id, target_name):
    """Move all recipes from source category to target, then soft-delete source."""
    # Get all recipes in the source category
    source_recipes = cursor.execute(
        "SELECT Z_12RECIPES FROM Z_12CATEGORIES WHERE Z_13CATEGORIES = ?",
        (source_id,),
    ).fetchall()
    source_recipe_ids = [r[0] for r in source_recipes]

    # Get recipes already in target
    target_recipes = cursor.execute(
        "SELECT Z_12RECIPES FROM Z_12CATEGORIES WHERE Z_13CATEGORIES = ?",
        (target_id,),
    ).fetchall()
    target_recipe_ids = set(r[0] for r in target_recipes)

    # Add missing recipes to target
    added = 0
    for recipe_id in source_recipe_ids:
        if recipe_id not in target_recipe_ids:
            cursor.execute(
                "INSERT INTO Z_12CATEGORIES (Z_12RECIPES, Z_13CATEGORIES) VALUES (?, ?)",
                (recipe_id, target_id),
            )
            added += 1

    # Delete all source associations
    cursor.execute("DELETE FROM Z_12CATEGORIES WHERE Z_13CATEGORIES = ?", (source_id,))

    # Mark all affected recipes as modified for sync
    all_affected = set(source_recipe_ids) | target_recipe_ids
    for recipe_id in all_affected:
        cursor.execute(
            """
            UPDATE ZRECIPE
            SET Z_OPT = Z_OPT + 1, ZISSYNCED = 0,
                ZSTATUS = 'modified', ZSYNCHASH = ?
            WHERE Z_PK = ? AND ZINTRASH = 0
            """,
            (_new_sync_hash(), recipe_id),
        )

    # Soft-delete the source category
    cursor.execute(
        """
        UPDATE ZRECIPECATEGORY
        SET ZSTATUS = 'deleted', ZISSYNCED = 0, Z_OPT = Z_OPT + 1
        WHERE Z_PK = ?
        """,
        (source_id,),
    )

    print(f"  Merged '{source_name}' ({len(source_recipe_ids)} recipes) → '{target_name}'")
    print(f"    {added} new associations added, {len(source_recipe_ids) - added} already existed")
    print(f"    '{source_name}' category deleted")


def main():
    # Pre-flight check (read-only)
    ro = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    print("=== Pre-flight check ===")
    for cat_id, name in [(134, "AAA Easy/Quick"), (13, "Weekday"), (8, "AAA Up Next"), (17, "Try Soon")]:
        row = ro.execute("SELECT Z_PK, ZNAME FROM ZRECIPECATEGORY WHERE Z_PK = ?", (cat_id,)).fetchone()
        count = ro.execute("SELECT COUNT(*) as cnt FROM Z_12CATEGORIES WHERE Z_13CATEGORIES = ?", (cat_id,)).fetchone()["cnt"]
        print(f"  {row['ZNAME']} (id={cat_id}): {count} recipes")
    ro.close()

    print("\n=== Merging ===")
    _kill_paprika()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    merge_category(cursor, 134, "AAA Easy/Quick", 13, "Weekday")
    print()
    merge_category(cursor, 8, "AAA Up Next", 17, "Try Soon")

    conn.commit()
    conn.close()

    _open_paprika()
    print("\nDone!")


if __name__ == "__main__":
    main()
