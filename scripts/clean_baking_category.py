#!/usr/bin/env python3
"""Remove 22 non-bakery items from the Baking category."""

import os
import sqlite3
import subprocess
import time

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/"
    "72KVKW69K8.com.hindsightlabs.paprika.mac.v3/"
    "Data/Database/Paprika.sqlite"
)

RECIPES_TO_REMOVE = [
    "Moroccan Spiced Vegetable Couscous",
    "One-Pan Orzo with Spinach and Feta",
    "One-Pan Zucchini-Pesto Orzo",
    "One-Pot Tortellini with Prosciutto and Peas",
    "Pad Krapow Gai (Thai Basil Chicken)",
    "Paprika Chicken and Potatoes",
    "Pesto Beans",
    "Poulet Vallée D'Auge",
    "Red Cabbage Ragù",
    "Red Cabbage with Walnuts and Feta",
    "Macaroni Salad",
    "Mulligatawny Soup",
    "Pasta Frittata",
    "Peanut Butter Noodles",
    "Penne with Brussels Sprouts, Chile and Pancetta",
    "Penne with Roasted Cherry Tomatoes",
    "Pinch Hitter (cocktail)",
    "Potato Crust for Fish",
    "Potato Kugel",
    "Skillet Vegetable Potpie",
    "Spoonbread",
    "Vertamae Smart-Grosvenor's Onion Pie",
]


def main():
    # Pre-flight: get recipe and category IDs
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    baking_cat = conn.execute(
        "SELECT Z_PK FROM ZRECIPECATEGORY WHERE ZNAME = 'Baking' AND (ZSTATUS IS NULL OR ZSTATUS != 'deleted')"
    ).fetchone()

    if not baking_cat:
        print("ERROR: Baking category not found")
        conn.close()
        return

    baking_id = baking_cat["Z_PK"]

    # Get recipe IDs
    recipe_ids = {}
    for recipe_name in RECIPES_TO_REMOVE:
        row = conn.execute(
            "SELECT Z_PK FROM ZRECIPE WHERE ZNAME = ? AND ZINTRASH = 0",
            (recipe_name,),
        ).fetchone()
        if row:
            recipe_ids[recipe_name] = row["Z_PK"]
        else:
            print(f"WARNING: Recipe not found: {recipe_name}")

    print(f"=== Pre-flight check ===")
    for name, recipe_id in recipe_ids.items():
        print(f"  OK: {name}")

    conn.close()

    # Apply changes
    print("\nKilling Paprika...")
    subprocess.run(["killall", "Paprika Recipe Manager 3"], stderr=subprocess.DEVNULL, check=False)
    time.sleep(0.8)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000")
    cursor = conn.cursor()

    removed = 0
    for recipe_id in recipe_ids.values():
        cursor.execute(
            "DELETE FROM Z_12CATEGORIES WHERE Z_12RECIPES = ? AND Z_13CATEGORIES = ?",
            (recipe_id, baking_id),
        )
        removed += 1

    conn.commit()
    conn.close()

    subprocess.run(["open", "-a", "Paprika Recipe Manager 3"], stderr=subprocess.DEVNULL, check=False)

    print(f"\n=== REMOVED ===")
    print(f"Baking category removed from: {removed} recipes")
    print("Done!")


if __name__ == "__main__":
    main()
