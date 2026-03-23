#!/usr/bin/env python3
"""Force-sync all recipes to all devices.

Marks every non-trashed recipe as modified with a new ZSYNCHASH so Paprika's
sync engine treats this Mac as authoritative and pushes all data to other devices.
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


def main():
    # Get count of recipes to sync
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    recipe_ids = [
        row["Z_PK"]
        for row in conn.execute("SELECT Z_PK FROM ZRECIPE WHERE ZINTRASH = 0").fetchall()
    ]
    conn.close()

    print(f"Found {len(recipe_ids)} non-trashed recipes to mark for sync.")
    print("\nKilling Paprika...")
    _kill_paprika()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    cursor = conn.cursor()

    for recipe_id in recipe_ids:
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

    print(f"Marked {len(recipe_ids)} recipes as modified.")
    print("Opening Paprika...")
    _open_paprika()
    print("Done! Paprika will now sync all recipes to other devices.")


if __name__ == "__main__":
    main()
