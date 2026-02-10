"""Paprika 3 MCP Server — tools for meal planning and recipe management."""

import json
import os
import re
import sqlite3
import subprocess
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# --- Configuration ---

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/"
    "72KVKW69K8.com.hindsightlabs.paprika.mac.v3/"
    "Data/Database/Paprika.sqlite"
)

mcp = FastMCP("paprika")

# --- Helpers ---

_DATE_RE = re.compile(r"^(?:zz)?(\d{8})\b")


def _get_db(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the Paprika database."""
    if read_only:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_menu_date(category_name: str) -> date | None:
    """Extract a date from a category name like 'zz20211003 Menu' or '20260131 Menu'."""
    m = _DATE_RE.match(category_name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _get_categories_for_recipe(conn: sqlite3.Connection, recipe_pk: int) -> list[dict]:
    """Return all categories for a recipe, split into regular and date categories."""
    rows = conn.execute(
        """
        SELECT c.ZNAME
        FROM ZRECIPECATEGORY c
        JOIN Z_12CATEGORIES jt ON jt.Z_13CATEGORIES = c.Z_PK
        WHERE jt.Z_12RECIPES = ?
        """,
        (recipe_pk,),
    ).fetchall()

    categories = []
    date_categories = []
    for row in rows:
        name = row["ZNAME"]
        parsed = _parse_menu_date(name)
        if parsed:
            date_categories.append((parsed, name))
        else:
            categories.append(name)
    return categories, date_categories


def _last_made(date_categories: list[tuple[date, str]]) -> tuple[str | None, int | None]:
    """From a list of (date, name) tuples, return (last_made_date_str, days_since)."""
    if not date_categories:
        return None, None
    most_recent = max(date_categories, key=lambda x: x[0])
    d = most_recent[0]
    days = (date.today() - d).days
    return d.isoformat(), days


def _preference_score(
    rating: int, is_favorite: bool, is_tried_and_true: bool
) -> int:
    """Compute composite preference score (0-7)."""
    score = rating or 0
    if is_favorite:
        score += 1
    if is_tried_and_true:
        score += 1
    return score


def _recipe_to_dict(
    conn: sqlite3.Connection, row: sqlite3.Row, include_full: bool = False
) -> dict:
    """Convert a recipe DB row to a clean dict."""
    pk = row["Z_PK"]
    categories, date_categories = _get_categories_for_recipe(conn, pk)
    is_tried_and_true = "Tried and True" in categories
    is_favorite = bool(row["ZONFAVORITES"])
    score = _preference_score(row["ZRATING"], is_favorite, is_tried_and_true)
    last_made_date, days_since = _last_made(date_categories)

    result = {
        "id": pk,
        "name": (row["ZNAME"] or "").rstrip("."),
        "preference_score": score,
        "categories": categories,
        "cook_time": row["ZCOOKTIME"] or None,
        "prep_time": row["ZPREPTIME"] or None,
        "servings": row["ZSERVINGS"] or None,
        "last_made_date": last_made_date,
        "days_since_last_made": days_since,
        "notes": row["ZNOTES"] or None,
    }

    if include_full:
        result["ingredients"] = row["ZINGREDIENTS"] or None
        result["directions"] = row["ZDIRECTIONS"] or None
        result["total_time"] = row["ZTOTALTIME"] or None

    return result


# --- Tools ---


@mcp.tool()
def search_recipes(
    query: str | None = None,
    category: str | None = None,
    min_score: int = 0,
    max_results: int = 20,
) -> str:
    """Search Paprika recipes by keyword and/or category.

    Args:
        query: Optional keyword to search in recipe names and ingredients (case-insensitive substring match).
        category: Optional category name to filter by (e.g. "Vegetarian", "Fish", "Chicken", "Dessert").
        min_score: Minimum preference score (0-7). Preference score = star rating (0-5) + 1 if Tried and True + 1 if Favorited.
        max_results: Maximum number of results to return (default 20).
    """
    conn = _get_db()
    try:
        # Build query
        sql = "SELECT r.* FROM ZRECIPE r WHERE r.ZINTRASH = 0"
        params: list = []

        if query:
            sql += " AND (r.ZNAME LIKE ? OR r.ZINGREDIENTS LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like])

        if category:
            sql += """
                AND r.Z_PK IN (
                    SELECT jt.Z_12RECIPES
                    FROM Z_12CATEGORIES jt
                    JOIN ZRECIPECATEGORY c ON c.Z_PK = jt.Z_13CATEGORIES
                    WHERE c.ZNAME LIKE ?
                )
            """
            params.append(f"%{category}%")

        rows = conn.execute(sql, params).fetchall()

        # Convert and score
        recipes = []
        for row in rows:
            recipe = _recipe_to_dict(conn, row)
            if recipe["preference_score"] >= min_score:
                recipes.append(recipe)

        # Sort: preference_score desc, then days_since_last_made desc (prefer not-recently-made)
        recipes.sort(
            key=lambda r: (
                r["preference_score"],
                r["days_since_last_made"] or 99999,
            ),
            reverse=True,
        )

        recipes = recipes[:max_results]
        return json.dumps(recipes, indent=2)
    finally:
        conn.close()


@mcp.tool()
def get_recipe_details(recipe_name: str) -> str:
    """Get full details for a specific recipe including ingredients and directions.

    Args:
        recipe_name: The recipe name to look up (case-insensitive, partial match supported).
    """
    conn = _get_db()
    try:
        # Try exact match first, then partial
        row = conn.execute(
            "SELECT * FROM ZRECIPE WHERE ZINTRASH = 0 AND ZNAME LIKE ? LIMIT 1",
            (f"%{recipe_name}%",),
        ).fetchone()

        if not row:
            return json.dumps({"error": f"No recipe found matching '{recipe_name}'"})

        recipe = _recipe_to_dict(conn, row, include_full=True)
        return json.dumps(recipe, indent=2)
    finally:
        conn.close()


@mcp.tool()
def get_meal_history(weeks_back: int = 8) -> str:
    """Get recent meal planning history showing what recipes were made and when.

    Args:
        weeks_back: How many weeks of history to return (default 8).
    """
    conn = _get_db()
    try:
        cutoff = date.today() - timedelta(weeks=weeks_back)

        # Get all date-based categories
        categories = conn.execute(
            "SELECT Z_PK, ZNAME FROM ZRECIPECATEGORY"
        ).fetchall()

        menus = []
        for cat in categories:
            d = _parse_menu_date(cat["ZNAME"])
            if not d or d < cutoff:
                continue

            # Get recipes in this category
            recipes = conn.execute(
                """
                SELECT r.ZNAME
                FROM ZRECIPE r
                JOIN Z_12CATEGORIES jt ON jt.Z_12RECIPES = r.Z_PK
                WHERE jt.Z_13CATEGORIES = ? AND r.ZINTRASH = 0
                """,
                (cat["Z_PK"],),
            ).fetchall()

            # Extract label (the part after the date)
            label = _DATE_RE.sub("", cat["ZNAME"]).strip()

            menus.append({
                "category_id": cat["Z_PK"],
                "category_name": cat["ZNAME"],
                "date": d.isoformat(),
                "label": label or "Menu",
                "recipes": [r["ZNAME"].rstrip(".") for r in recipes],
            })

        menus.sort(key=lambda m: m["date"], reverse=True)
        return json.dumps(menus, indent=2)
    finally:
        conn.close()


@mcp.tool()
def create_meal_plan(
    date_str: str, recipe_ids: list[int], label: str = "Menu"
) -> str:
    """Create a new meal plan by tagging recipes with a date-based category.

    This creates a new category with the format "YYYYMMDD {label}" and associates
    the specified recipes with it. The app will be restarted automatically to
    display the new meal plan.

    Args:
        date_str: Date in YYYY-MM-DD format (e.g., "2026-02-15")
        recipe_ids: List of recipe Z_PK IDs to include in the meal plan
        label: Label for the meal (default "Menu", can be "Dinner", "BIRTHDAY menu", etc.)

    Returns:
        JSON with details about the created meal plan
    """
    conn = _get_db(read_only=False)
    try:
        # Parse and format the date
        meal_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        category_name = f"{meal_date.strftime('%Y%m%d')} {label}"

        # Get the next available category ID
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(Z_PK) FROM ZRECIPECATEGORY")
        max_pk = cursor.fetchone()[0]
        new_category_pk = (max_pk or 0) + 1

        # Generate UUID for the category
        category_uuid = str(uuid.uuid4()).upper()

        # Insert the new category with ZISSYNCED=0 to mark it as a local change
        cursor.execute(
            """
            INSERT INTO ZRECIPECATEGORY
            (Z_PK, Z_ENT, Z_OPT, ZISSYNCED, ZORDERFLAG, ZPARENT, ZNAME, ZSTATUS, ZUID)
            VALUES (?, 13, 1, 0, 0, NULL, ?, 'unmodified', ?)
            """,
            (new_category_pk, category_name, category_uuid),
        )

        # Update Z_PRIMARYKEY table
        cursor.execute(
            """
            UPDATE Z_PRIMARYKEY
            SET Z_MAX = ?
            WHERE Z_NAME = 'RecipeCategory'
            """,
            (new_category_pk,),
        )

        # Link recipes to the category via the join table
        for recipe_id in recipe_ids:
            cursor.execute(
                """
                INSERT INTO Z_12CATEGORIES (Z_12RECIPES, Z_13CATEGORIES)
                VALUES (?, ?)
                """,
                (recipe_id, new_category_pk),
            )

        conn.commit()

        # Get recipe names for the response
        recipe_names = []
        for recipe_id in recipe_ids:
            row = cursor.execute(
                "SELECT ZNAME FROM ZRECIPE WHERE Z_PK = ?", (recipe_id,)
            ).fetchone()
            if row:
                recipe_names.append(row["ZNAME"].rstrip("."))

        result = {
            "category_id": new_category_pk,
            "category_name": category_name,
            "date": date_str,
            "recipes_added": recipe_names,
            "recipe_count": len(recipe_names),
        }

        # Restart Paprika to make the changes visible
        try:
            subprocess.run(
                ["killall", "Paprika Recipe Manager 3"],
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ["open", "-a", "Paprika Recipe Manager 3"], check=True
            )
            result["app_restarted"] = True
        except Exception as e:
            result["app_restarted"] = False
            result["restart_error"] = str(e)

        return json.dumps(result, indent=2)

    finally:
        conn.close()


@mcp.tool()
def add_recipe_to_category(recipe_id: int, category_id: int) -> str:
    """Add a recipe to an existing category (tag the recipe with the category).

    Args:
        recipe_id: The recipe Z_PK ID to add
        category_id: The category Z_PK ID to add the recipe to

    Returns:
        JSON with confirmation of the operation
    """
    conn = _get_db(read_only=False)
    try:
        cursor = conn.cursor()

        # Check if the relationship already exists
        existing = cursor.execute(
            """
            SELECT * FROM Z_12CATEGORIES
            WHERE Z_12RECIPES = ? AND Z_13CATEGORIES = ?
            """,
            (recipe_id, category_id),
        ).fetchone()

        if existing:
            # Get names for the message
            recipe = cursor.execute(
                "SELECT ZNAME FROM ZRECIPE WHERE Z_PK = ?", (recipe_id,)
            ).fetchone()
            category = cursor.execute(
                "SELECT ZNAME FROM ZRECIPECATEGORY WHERE Z_PK = ?", (category_id,)
            ).fetchone()

            return json.dumps({
                "success": False,
                "message": f"Recipe '{recipe['ZNAME'].rstrip('.')}' is already in category '{category['ZNAME']}'",
            })

        # Add the relationship
        cursor.execute(
            """
            INSERT INTO Z_12CATEGORIES (Z_12RECIPES, Z_13CATEGORIES)
            VALUES (?, ?)
            """,
            (recipe_id, category_id),
        )
        conn.commit()

        # Get names for confirmation
        recipe = cursor.execute(
            "SELECT ZNAME FROM ZRECIPE WHERE Z_PK = ?", (recipe_id,)
        ).fetchone()
        category = cursor.execute(
            "SELECT ZNAME FROM ZRECIPECATEGORY WHERE Z_PK = ?", (category_id,)
        ).fetchone()

        result = {
            "success": True,
            "recipe_name": recipe["ZNAME"].rstrip("."),
            "category_name": category["ZNAME"],
        }

        # Restart Paprika to make the changes visible
        try:
            subprocess.run(
                ["killall", "Paprika Recipe Manager 3"],
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ["open", "-a", "Paprika Recipe Manager 3"], check=True
            )
            result["app_restarted"] = True
        except Exception as e:
            result["app_restarted"] = False
            result["restart_error"] = str(e)

        return json.dumps(result, indent=2)

    finally:
        conn.close()


@mcp.tool()
def remove_recipe_from_category(recipe_id: int, category_id: int) -> str:
    """Remove a recipe from a category (untag the recipe from the category).

    Args:
        recipe_id: The recipe Z_PK ID to remove
        category_id: The category Z_PK ID to remove the recipe from

    Returns:
        JSON with confirmation of the operation
    """
    conn = _get_db(read_only=False)
    try:
        cursor = conn.cursor()

        # Get names before deleting
        recipe = cursor.execute(
            "SELECT ZNAME FROM ZRECIPE WHERE Z_PK = ?", (recipe_id,)
        ).fetchone()
        category = cursor.execute(
            "SELECT ZNAME FROM ZRECIPECATEGORY WHERE Z_PK = ?", (category_id,)
        ).fetchone()

        # Delete the relationship
        cursor.execute(
            """
            DELETE FROM Z_12CATEGORIES
            WHERE Z_12RECIPES = ? AND Z_13CATEGORIES = ?
            """,
            (recipe_id, category_id),
        )

        deleted_count = cursor.rowcount
        conn.commit()

        result = {
            "success": deleted_count > 0,
            "recipe_name": recipe["ZNAME"].rstrip(".") if recipe else None,
            "category_name": category["ZNAME"] if category else None,
            "message": f"Removed recipe from category" if deleted_count > 0 else "Recipe was not in this category",
        }

        # Restart Paprika to make the changes visible
        if deleted_count > 0:
            try:
                subprocess.run(
                    ["killall", "Paprika Recipe Manager 3"],
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                subprocess.run(
                    ["open", "-a", "Paprika Recipe Manager 3"], check=True
                )
                result["app_restarted"] = True
            except Exception as e:
                result["app_restarted"] = False
                result["restart_error"] = str(e)

        return json.dumps(result, indent=2)

    finally:
        conn.close()


@mcp.tool()
def delete_category(category_id: int) -> str:
    """Delete a category and remove all recipe associations with it.

    This will delete the category and clean up all references in the join table,
    but will NOT delete the recipes themselves.

    Args:
        category_id: The category Z_PK ID to delete

    Returns:
        JSON with confirmation of the operation
    """
    conn = _get_db(read_only=False)
    try:
        cursor = conn.cursor()

        # Get category name before deleting
        category = cursor.execute(
            "SELECT ZNAME FROM ZRECIPECATEGORY WHERE Z_PK = ?", (category_id,)
        ).fetchone()

        if not category:
            return json.dumps({
                "success": False,
                "message": f"Category with ID {category_id} not found",
            })

        category_name = category["ZNAME"]

        # Delete all recipe associations
        cursor.execute(
            "DELETE FROM Z_12CATEGORIES WHERE Z_13CATEGORIES = ?",
            (category_id,),
        )
        recipes_unlinked = cursor.rowcount

        # Delete the category itself
        cursor.execute(
            "DELETE FROM ZRECIPECATEGORY WHERE Z_PK = ?",
            (category_id,),
        )

        conn.commit()

        result = {
            "success": True,
            "category_name": category_name,
            "recipes_unlinked": recipes_unlinked,
            "message": f"Deleted category '{category_name}' and unlinked {recipes_unlinked} recipe(s)",
        }

        # Restart Paprika to make the changes visible
        try:
            subprocess.run(
                ["killall", "Paprika Recipe Manager 3"],
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ["open", "-a", "Paprika Recipe Manager 3"], check=True
            )
            result["app_restarted"] = True
        except Exception as e:
            result["app_restarted"] = False
            result["restart_error"] = str(e)

        return json.dumps(result, indent=2)

    finally:
        conn.close()


# --- Entry point ---

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
