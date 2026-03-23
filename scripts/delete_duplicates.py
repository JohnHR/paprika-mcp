#!/usr/bin/env python3
"""Delete confirmed duplicate recipes from the Paprika database.

Follows the same soft-delete + sync pattern used by the MCP server:
- Remove category associations from Z_12CATEGORIES
- Set ZINTRASH=1, ZSTATUS='deleted', ZISSYNCED=0 on the recipe
- Increment Z_OPT and set a fresh ZSYNCHASH
- Kill/reopen Paprika around the write
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

# Confirmed duplicates to remove (recipe Z_PK ids)
RECIPES_TO_DELETE = {
    704: "Baked Beans (dup of 538)",
    1011: "Peanut Butter Noodles (dup of 875)",
    575: "Peanut Butter Overnight Oats [eatingbirdfood] (dup of 228)",
    667: "Perfect Peach Pie (dup of 832)",
    164: "Turkey Chili (dup of 919)",
    559: "Heirloom Tomato Tart / Corn Salad URL dup (dup of 561)",
    118: "Roasted Brussels Sprouts with Garlic (dup of 910)",
    907: "Creme Brulee (dup of 583)",
}


def _new_sync_hash() -> str:
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest().upper()


def _kill_paprika() -> None:
    subprocess.run(
        ["killall", "Paprika Recipe Manager 3"],
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(0.8)


def _open_paprika() -> None:
    subprocess.run(
        ["open", "-a", "Paprika Recipe Manager 3"],
        stderr=subprocess.DEVNULL,
        check=False,
    )


def main():
    # First, verify all recipes exist and are not already trashed (read-only check)
    ro_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    ro_conn.row_factory = sqlite3.Row
    print("=== Pre-flight check (read-only) ===")
    for recipe_id, label in RECIPES_TO_DELETE.items():
        row = ro_conn.execute(
            "SELECT Z_PK, ZNAME, ZINTRASH FROM ZRECIPE WHERE Z_PK = ?",
            (recipe_id,),
        ).fetchone()
        if row is None:
            print(f"  ERROR: Recipe {recipe_id} ({label}) not found in database!")
            ro_conn.close()
            return
        if row["ZINTRASH"] == 1:
            print(f"  SKIP: Recipe {recipe_id} ({row['ZNAME']}) already in trash")
        else:
            print(f"  OK: Recipe {recipe_id} - {row['ZNAME']}")
    ro_conn.close()

    # Kill Paprika, do writes, reopen
    print("\n=== Killing Paprika ===")
    _kill_paprika()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("\n=== Deleting duplicates ===")
    for recipe_id, label in RECIPES_TO_DELETE.items():
        # Check not already trashed
        row = cursor.execute(
            "SELECT ZNAME, ZINTRASH FROM ZRECIPE WHERE Z_PK = ?",
            (recipe_id,),
        ).fetchone()
        if row["ZINTRASH"] == 1:
            print(f"  SKIP (already trashed): {recipe_id} - {row['ZNAME']}")
            continue

        # Remove category associations
        cat_count = cursor.execute(
            "SELECT COUNT(*) as cnt FROM Z_12CATEGORIES WHERE Z_12RECIPES = ?",
            (recipe_id,),
        ).fetchone()["cnt"]
        cursor.execute(
            "DELETE FROM Z_12CATEGORIES WHERE Z_12RECIPES = ?",
            (recipe_id,),
        )

        # Soft-delete the recipe
        sync_hash = _new_sync_hash()
        cursor.execute(
            """
            UPDATE ZRECIPE
            SET ZINTRASH = 1,
                ZSTATUS = 'deleted',
                ZISSYNCED = 0,
                Z_OPT = Z_OPT + 1,
                ZSYNCHASH = ?
            WHERE Z_PK = ?
            """,
            (sync_hash, recipe_id),
        )
        print(f"  DELETED: {recipe_id} - {row['ZNAME']} (removed {cat_count} category links)")

    conn.commit()
    conn.close()

    print("\n=== Reopening Paprika ===")
    _open_paprika()
    print("\nDone! Deleted", len(RECIPES_TO_DELETE), "duplicate recipes.")


if __name__ == "__main__":
    main()
