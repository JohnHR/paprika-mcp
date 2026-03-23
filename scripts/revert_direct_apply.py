#!/usr/bin/env python3
"""Revert the changes made by apply_categories_final.py (direct DB write).

Reads category_staging_final.json and reverses every add/remove so the DB
is back to its pre-apply state, ready for the MCP-tool-based apply pass.
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
    with open(STAGING_PATH) as f:
        staging = json.load(f)

    changes = [c for c in staging["changes"] if c.get("add") or c.get("remove")]
    print(f"Reverting changes for {len(changes)} recipes...")

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    categories = conn.execute(
        "SELECT Z_PK, ZNAME FROM ZRECIPECATEGORY WHERE ZSTATUS IS NULL OR ZSTATUS != 'deleted'"
    ).fetchall()
    cat_name_to_id = {row["ZNAME"]: row["Z_PK"] for row in categories}

    assocs = conn.execute("SELECT Z_12RECIPES, Z_13CATEGORIES FROM Z_12CATEGORIES").fetchall()
    existing_assocs = set((a["Z_12RECIPES"], a["Z_13CATEGORIES"]) for a in assocs)
    conn.close()

    print("Killing Paprika...")
    _kill_paprika()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    total_removed = 0
    total_added_back = 0
    total_skipped = 0
    affected_recipes = set()

    for change in changes:
        recipe_id = change["id"]

        # Reverse adds → delete them
        for cat_name in change.get("add", []):
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

        # Reverse removes → re-insert them
        for cat_name in change.get("remove", []):
            cat_id = cat_name_to_id[cat_name]
            if (recipe_id, cat_id) in existing_assocs:
                total_skipped += 1
                continue
            cursor.execute(
                "INSERT INTO Z_12CATEGORIES (Z_12RECIPES, Z_13CATEGORIES) VALUES (?, ?)",
                (recipe_id, cat_id),
            )
            existing_assocs.add((recipe_id, cat_id))
            total_added_back += 1
            affected_recipes.add(recipe_id)

    # Mark affected recipes as modified so Paprika sees the revert
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

    print(f"\n=== REVERTED ===")
    print(f"Recipes touched: {len(affected_recipes)}")
    print(f"Associations removed (were adds): {total_removed}")
    print(f"Associations re-added (were removes): {total_added_back}")
    print(f"Skipped (already in pre-apply state): {total_skipped}")
    print("DB is back to pre-apply state. Ready for MCP tool pass.")


if __name__ == "__main__":
    main()
