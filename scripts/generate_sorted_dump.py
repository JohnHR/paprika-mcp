#!/usr/bin/env python3
import sqlite3
import json
import os

db_path = os.path.expanduser("~/Library/Containers/com.hindsightlabs.paprika3/Data/Library/Application Support/Paprika3/paprika.db")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all recipes (not deleted)
cursor.execute("""
    SELECT Z_PK, ZNAME, ZSOURCEURL, ZRATING, ZISFAVORITED, ZPREPTIME, ZCOOKTIME, ZTOTALTIME, ZSERVINGS
    FROM ZRECIPE
    WHERE ZSTATUS IS NULL OR ZSTATUS != 'deleted'
    ORDER BY ZNAME COLLATE NOCASE
""")

recipes = []
for i, row in enumerate(cursor.fetchall()):
    recipe_id = row["Z_PK"]

    # Get ingredients
    cursor.execute("SELECT ZINGREDIENTS FROM ZRECIPE WHERE Z_PK = ?", (recipe_id,))
    ingredients_row = cursor.fetchone()
    ingredients = ingredients_row["ZINGREDIENTS"] or ""

    # Get directions
    cursor.execute("SELECT ZDIRECTIONS FROM ZRECIPE WHERE Z_PK = ?", (recipe_id,))
    directions_row = cursor.fetchone()
    directions = directions_row["ZDIRECTIONS"] or ""

    # Get categories
    cursor.execute("""
        SELECT ZRECIPECATEGORY.ZNAME FROM Z_12CATEGORIES
        JOIN ZRECIPECATEGORY ON Z_12CATEGORIES.Z_3CATEGORIES = ZRECIPECATEGORY.Z_PK
        WHERE Z_12CATEGORIES.Z_12RECIPES = ?
        ORDER BY ZRECIPECATEGORY.ZNAME
    """, (recipe_id,))
    categories = [cat_row["ZNAME"] for cat_row in cursor.fetchall()]

    recipes.append({
        "index": i + 1,  # 1-based index for easy reference
        "id": recipe_id,
        "name": row["ZNAME"],
        "source_url": row["ZSOURCEURL"] or "",
        "rating": row["ZRATING"] or 0,
        "on_favorites": bool(row["ZISFAVORITED"]),
        "prep_time": row["ZPREPTIME"] or "",
        "cook_time": row["ZCOOKTIME"] or "",
        "total_time": row["ZTOTALTIME"] or "",
        "servings": row["ZSERVINGS"] or "",
        "categories": categories,
        "ingredients": ingredients,
        "directions": directions,
    })

conn.close()

# Write to file
output_path = "/Users/john.rogers/repo/Personal/paprika-mcp/data/recipes_dump_sorted.json"
with open(output_path, "w") as f:
    json.dump(recipes, f, indent=2)

print(f"Generated {len(recipes)} recipes in alphabetical order")
print(f"Saved to {output_path}")
