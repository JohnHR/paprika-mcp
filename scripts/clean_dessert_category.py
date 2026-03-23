#!/usr/bin/env python3
"""Remove 19 savory dishes incorrectly categorized as Dessert."""

import os
import sqlite3
import subprocess
import time

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/"
    "72KVKW69K8.com.hindsightlabs.paprika.mac.v3/"
    "Data/Database/Paprika.sqlite"
)

# Recipe IDs to remove from Dessert
RECIPES_TO_REMOVE = {
    54: "Moroccan Spiced Vegetable Couscous",
    65: "Mulligatawny Soup",
    71: "Maple-Roasted Squash with Sage and Lime for Two",
    308: "Pesto Chicken, Corn, and Avocado Bacon Pasta Salad",
    337: "Red Cabbage Ragù",
    386: "Mexican Street Corn Salad with Avocado",
    577: "Pad Krapow Gai (Thai Basil Chicken)",
    581: "Pumpkin Chili",
    586: "Red Lentil Soup with Lemon (34k reviews)",
    665: "One-Pan Zucchini-Pesto Orzo",
    726: "Menemen (Turkish Scrambled Eggs with Tomato)",
    782: "No Chop Roast Butternut Pumpkin / Squash Soup",
    855: "Pasta Frittata",
    864: "Paprika Chicken and Potatoes",
    875: "Peanut Butter Noodles",
    904: "One-Pan Chickpea & Curry Shakshuka with Tomatoes & Spinach",
    935: "One-Pan Orzo with Spinach and Feta",
    941: "Mustard-Glazed Pork Tenderloin",
    958: "Miso-Maple Sheet-Pan Chicken with Brussels Sprouts",
}


def _kill_paprika() -> None:
    subprocess.run(
        ["killall", "Paprika Recipe Manager 3"],
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(0.8)


def _open_paprika() -> None:
    subprocess.Popen([
        "open", "-a", "Paprika Recipe Manager 3"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)


# Kill Paprika
_kill_paprika()

# Connect and remove
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get Dessert category ID
cursor.execute("SELECT Z_PK FROM ZRECIPECATEGORY WHERE ZNAME = 'Dessert'")
dessert_id = cursor.fetchone()[0]

print(f"Dessert category ID: {dessert_id}\n")

# Verify and remove
removed = []
for recipe_id, recipe_name in RECIPES_TO_REMOVE.items():
    # Check if association exists
    cursor.execute(
        "SELECT * FROM Z_12CATEGORIES WHERE Z_12RECIPES = ? AND Z_13CATEGORIES = ?",
        (recipe_id, dessert_id)
    )
    if cursor.fetchone():
        cursor.execute(
            "DELETE FROM Z_12CATEGORIES WHERE Z_12RECIPES = ? AND Z_13CATEGORIES = ?",
            (recipe_id, dessert_id)
        )
        removed.append(recipe_name)
        print(f"✓ Removed: {recipe_name}")
    else:
        print(f"✗ Not found: {recipe_name}")

conn.commit()
conn.close()

print(f"\n=== DONE ===")
print(f"Removed {len(removed)} recipes from Dessert category")

# Reopen Paprika
_open_paprika()
