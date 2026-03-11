"""Paprika 3 MCP Server — tools for meal planning and recipe management."""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
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

mcp = FastMCP("paprika", instructions="""\
This server manages recipes and meal plans in the Paprika 3 app.

WHAT A "MEAL PLAN" IS:
- A meal plan is a batch of 4-6 recipes that get entered as a single date-based \
category in Paprika (e.g. "20260309 Menu"). It represents roughly a week of meals.
- We do NOT assign recipes to specific days. The family picks from the list \
throughout the week. Never ask "what day is this for?" or try to map recipes to days.

MEAL PLANNING WORKFLOW:
- Always call get_meal_history BEFORE suggesting meals. This is the most \
important rule. Never recommend recipes the family just had.
- NEVER call create_meal_plan until the user has reviewed and approved the \
final list. Present the proposed 4-6 recipes, discuss substitutions, and only \
write to Paprika once the user says go.
- Batch all recipes into a single create_meal_plan call. Each write operation \
kills and restarts the Paprika app, so multiple calls means multiple restarts.

SEARCHING:
- search_recipes is for browsing and narrowing down options. It returns names, \
scores, categories, and last-made dates — enough to discuss options.
- Only call get_recipe_details when the user actually wants to see ingredients \
or directions (e.g. they're about to cook, or want to check what's in something).
- The query parameter matches against both recipe names AND ingredient lists. \
A search for "chicken" finds recipes named "Chicken Parmesan" AND recipes that \
list chicken as an ingredient.
- Use the category parameter to filter by type (e.g. "Vegetarian", "Fish", \
"Chicken", "Dessert"). Use the query parameter for specific ingredients or dishes.
- For "what should we make?" questions, use min_score=4 to surface family \
favorites. For broader exploration, use the default (0).

PREFERENCE SCORES:
- Score ranges 0-7: star rating (0-5) + 1 if "Tried and True" + 1 if Favorited.
- Higher scores = family favorites. Results are pre-sorted by score descending, \
then by staleness (longest since last made first).
- days_since_last_made is valuable context. Mention it naturally when presenting \
options ("you haven't made X in 3 months").

CATEGORIES & MEAL PLANS:
- Categories are tags — a recipe can belong to many. Regular categories \
(Chicken, Vegetarian, etc.) classify recipes. Date-based categories \
(YYYYMMDD Label) ARE meal plans.
- Use label "Menu" for normal meal plans. Use descriptive labels for special \
occasions ("Birthday dinner", "Thanksgiving").
- add_recipe_to_category / remove_recipe_from_category are for editing EXISTING \
meal plans or managing recipe tags. Don't use them to build a new meal plan \
one recipe at a time — use create_meal_plan instead.
- delete_category removes a meal plan or tag entirely. Confirm with the user first.
""")

# --- Helpers ---

_DATE_RE = re.compile(r"^(?:zz)?(\d{8})\b")


def _get_db(read_only: bool = True) -> sqlite3.Connection:
    """Open a connection to the Paprika database."""
    if read_only:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    return conn


def _new_sync_hash() -> str:
    """Generate a new random sync hash (how Paprika marks recipes as changed)."""
    return hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest().upper()


def _kill_paprika() -> None:
    """Kill the Paprika app so it releases its DB lock before we write."""
    subprocess.run(
        ["killall", "Paprika Recipe Manager 3"],
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(0.8)  # give it time to fully close


def _open_paprika() -> None:
    subprocess.run(
        ["open", "-a", "Paprika Recipe Manager 3"],
        stderr=subprocess.DEVNULL,
        check=False,
    )


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
    # Kill Paprika before opening the DB for writing so it releases its lock.
    _kill_paprika()

    conn = _get_db(read_only=False)
    try:
        # Parse and format the date
        meal_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        category_name = f"{meal_date.strftime('%Y%m%d')} {label}"

        cursor = conn.cursor()

        # Idempotency: if this category already exists, reuse it instead of
        # creating a duplicate.
        existing = cursor.execute(
            "SELECT Z_PK FROM ZRECIPECATEGORY WHERE ZNAME = ?",
            (category_name,),
        ).fetchone()

        if existing:
            new_category_pk = existing["Z_PK"]
            created = False
        else:
            # Derive a safe PK: take the higher of Z_PRIMARYKEY and the actual
            # table max so we never collide with an in-flight Paprika write.
            pk_row = cursor.execute(
                "SELECT Z_MAX FROM Z_PRIMARYKEY WHERE Z_NAME = 'RecipeCategory'"
            ).fetchone()
            pk_from_table = pk_row["Z_MAX"] if pk_row else 0

            cursor.execute("SELECT MAX(Z_PK) FROM ZRECIPECATEGORY")
            max_pk = cursor.fetchone()[0] or 0

            new_category_pk = max(pk_from_table, max_pk) + 1

            # Generate UUID for the category
            category_uuid = str(uuid.uuid4()).upper()

            # ZSTATUS='new' tells Paprika this record needs to be uploaded on
            # the next sync cycle. ZISSYNCED=0 reinforces that it hasn't been
            # pushed to the cloud yet.
            cursor.execute(
                """
                INSERT INTO ZRECIPECATEGORY
                (Z_PK, Z_ENT, Z_OPT, ZISSYNCED, ZORDERFLAG, ZPARENT, ZNAME, ZSTATUS, ZUID)
                VALUES (?, 13, 1, 0, 0, NULL, ?, 'new', ?)
                """,
                (new_category_pk, category_name, category_uuid),
            )

            # Keep Z_PRIMARYKEY in sync
            cursor.execute(
                """
                UPDATE Z_PRIMARYKEY SET Z_MAX = ?
                WHERE Z_NAME = 'RecipeCategory'
                """,
                (new_category_pk,),
            )
            created = True

        # Link recipes to the category, skipping any that are already linked.
        linked_ids = []
        for recipe_id in recipe_ids:
            already_linked = cursor.execute(
                """
                SELECT 1 FROM Z_12CATEGORIES
                WHERE Z_12RECIPES = ? AND Z_13CATEGORIES = ?
                """,
                (recipe_id, new_category_pk),
            ).fetchone()
            if not already_linked:
                cursor.execute(
                    """
                    INSERT INTO Z_12CATEGORIES (Z_12RECIPES, Z_13CATEGORIES)
                    VALUES (?, ?)
                    """,
                    (recipe_id, new_category_pk),
                )
                linked_ids.append(recipe_id)

        # Mark each newly-linked recipe as needing sync so the category
        # associations propagate to other devices.  The join table has no
        # sync fields of its own — associations travel with the recipe data.
        # ZSYNCHASH is a random change-detection token (not a content hash).
        # A new random hash creates a mismatch with the cloud, and combined
        # with ZSTATUS='modified', forces Paprika to upload the local version.
        for recipe_id in linked_ids:
            cursor.execute(
                """
                UPDATE ZRECIPE
                SET Z_OPT = Z_OPT + 1, ZISSYNCED = 0,
                    ZSTATUS = 'modified', ZSYNCHASH = ?
                WHERE Z_PK = ?
                """,
                (_new_sync_hash(), recipe_id),
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
            "category_created": created,
        }

    finally:
        conn.close()

    # Reopen Paprika after the connection is closed.
    _open_paprika()
    result["app_restarted"] = True
    return json.dumps(result, indent=2)


@mcp.tool()
def add_recipe_to_category(recipe_id: int, category_id: int) -> str:
    """Add a recipe to an existing category (tag the recipe with the category).

    Args:
        recipe_id: The recipe Z_PK ID to add
        category_id: The category Z_PK ID to add the recipe to

    Returns:
        JSON with confirmation of the operation
    """
    _kill_paprika()

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
            recipe = cursor.execute(
                "SELECT ZNAME FROM ZRECIPE WHERE Z_PK = ?", (recipe_id,)
            ).fetchone()
            category = cursor.execute(
                "SELECT ZNAME FROM ZRECIPECATEGORY WHERE Z_PK = ?", (category_id,)
            ).fetchone()

            conn.close()
            _open_paprika()
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

        # Mark recipe as needing sync so the association propagates.
        cursor.execute(
            """
            UPDATE ZRECIPE
            SET Z_OPT = Z_OPT + 1, ZISSYNCED = 0,
                ZSTATUS = 'modified', ZSYNCHASH = ?
            WHERE Z_PK = ?
            """,
            (_new_sync_hash(), recipe_id),
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

    finally:
        conn.close()

    _open_paprika()
    result["app_restarted"] = True
    return json.dumps(result, indent=2)


@mcp.tool()
def remove_recipe_from_category(recipe_id: int, category_id: int) -> str:
    """Remove a recipe from a category (untag the recipe from the category).

    Args:
        recipe_id: The recipe Z_PK ID to remove
        category_id: The category Z_PK ID to remove the recipe from

    Returns:
        JSON with confirmation of the operation
    """
    _kill_paprika()

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

        # Mark recipe as needing sync so the removal propagates.
        if deleted_count > 0:
            cursor.execute(
                """
                UPDATE ZRECIPE
                SET Z_OPT = Z_OPT + 1, ZISSYNCED = 0,
                    ZSTATUS = 'modified', ZSYNCHASH = ?
                WHERE Z_PK = ?
                """,
                (_new_sync_hash(), recipe_id),
            )

        conn.commit()

        result = {
            "success": deleted_count > 0,
            "recipe_name": recipe["ZNAME"].rstrip(".") if recipe else None,
            "category_name": category["ZNAME"] if category else None,
            "message": "Removed recipe from category" if deleted_count > 0 else "Recipe was not in this category",
        }

    finally:
        conn.close()

    _open_paprika()
    result["app_restarted"] = True
    return json.dumps(result, indent=2)


@mcp.tool()
def list_categories(query: str | None = None) -> str:
    """List all recipe categories with their IDs.

    Returns regular categories (not date-based meal plans). Use the ID
    to add/remove recipes from a category.

    Args:
        query: Optional substring to filter category names (case-insensitive).
    """
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT Z_PK, ZNAME FROM ZRECIPECATEGORY WHERE ZSTATUS != 'deleted' OR ZSTATUS IS NULL"
        ).fetchall()

        categories = []
        for row in rows:
            name = row["ZNAME"]
            if _parse_menu_date(name):
                continue  # skip date-based meal plan categories
            if query and query.lower() not in name.lower():
                continue
            categories.append({"id": row["Z_PK"], "name": name})

        categories.sort(key=lambda c: c["name"].lower())
        return json.dumps(categories, indent=2)
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
    _kill_paprika()

    conn = _get_db(read_only=False)
    try:
        cursor = conn.cursor()

        # Get category name before deleting
        category = cursor.execute(
            "SELECT ZNAME FROM ZRECIPECATEGORY WHERE Z_PK = ?", (category_id,)
        ).fetchone()

        if not category:
            conn.close()
            _open_paprika()
            return json.dumps({
                "success": False,
                "message": f"Category with ID {category_id} not found",
            })

        category_name = category["ZNAME"]

        # Find all recipes linked to this category so we can re-sync them.
        linked_recipes = cursor.execute(
            "SELECT Z_12RECIPES FROM Z_12CATEGORIES WHERE Z_13CATEGORIES = ?",
            (category_id,),
        ).fetchall()
        linked_ids = [r[0] for r in linked_recipes]

        # Delete all recipe associations
        cursor.execute(
            "DELETE FROM Z_12CATEGORIES WHERE Z_13CATEGORIES = ?",
            (category_id,),
        )
        recipes_unlinked = cursor.rowcount

        # Mark affected recipes as modified so they re-sync without
        # this category in their category list.
        for recipe_id in linked_ids:
            cursor.execute(
                """
                UPDATE ZRECIPE
                SET Z_OPT = Z_OPT + 1, ZISSYNCED = 0,
                    ZSTATUS = 'modified', ZSYNCHASH = ?
                WHERE Z_PK = ?
                """,
                (_new_sync_hash(), recipe_id),
            )

        # Soft-delete the category so the deletion syncs to other devices.
        cursor.execute(
            """
            UPDATE ZRECIPECATEGORY
            SET ZSTATUS = 'deleted', ZISSYNCED = 0, Z_OPT = Z_OPT + 1
            WHERE Z_PK = ?
            """,
            (category_id,),
        )

        conn.commit()

        result = {
            "success": True,
            "category_name": category_name,
            "recipes_unlinked": recipes_unlinked,
            "message": f"Deleted category '{category_name}' and unlinked {recipes_unlinked} recipe(s)",
        }

    finally:
        conn.close()

    _open_paprika()
    result["app_restarted"] = True
    return json.dumps(result, indent=2)


# --- AppleScript helpers ---


def _run_applescript(script: str) -> str:
    """Run an AppleScript via osascript and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _import_recipe_applescript(url: str, page_load_timeout: int = 8) -> str:
    """Build the AppleScript that drives Paprika's browser to import a recipe.

    Flow:
      1. Activate Paprika and click "Browser" in the sidebar
      2. Reset any stale scraper data
      3. Cmd+L to focus the address bar, set the URL, press Enter
      4. Wait for the page to load
      5. Click "Download" in the browser toolbar to scrape the recipe
      6. Wait for the recipe edit form to appear
      7. Click "Save" on the edit form to persist the recipe
    """
    return f'''
tell application "Paprika Recipe Manager 3" to activate
delay 0.5

tell application "System Events"
    tell process "Paprika Recipe Manager 3"
        set frontmost to true
        delay 0.3

        -- Step 1: Click "Browser" in the sidebar
        select row 3 of outline 1 of scroll area 1 of splitter group 1 of window 1
        delay 1

        -- Step 2: Reset any stale scraper data from a previous page
        try
            click button "Reset" of splitter group 1 of splitter group 1 of window 1
            delay 0.5
        end try

        -- Step 3: Focus address bar with Cmd+L, set URL, navigate
        keystroke "l" using command down
        delay 0.5
        set fe to value of attribute "AXFocusedUIElement"
        set value of fe to "{url}"
        delay 0.2
        key code 36
        delay {page_load_timeout}

        -- Step 4: Click "Download" in the browser toolbar to scrape the recipe
        -- This button is inside splitter group 1 of splitter group 1 (the browser view)
        click button "Download" of splitter group 1 of splitter group 1 of window 1
        delay 5

        -- Step 5: Wait for the recipe edit form to appear
        -- The edit form has a "Save" button at splitter group 1 of window 1 (one level up)
        set maxWait to 15
        set waited to 0
        repeat while waited < maxWait
            try
                set btnDesc to description of button "Save" of splitter group 1 of window 1
                if btnDesc is "Save Recipe" then exit repeat
            end try
            delay 1
            set waited to waited + 1
        end repeat

        -- Step 6: Click "Save" on the edit form to persist the recipe
        click button "Save" of splitter group 1 of window 1
        delay 1

        return "ok"
    end tell
end tell
'''


@mcp.tool()
def import_recipe(
    url: str,
    categories: list[str] | None = None,
    page_load_timeout: int = 8,
) -> str:
    """Import a recipe from a URL using Paprika's built-in browser and scraper.

    Automates Paprika's UI to navigate to the URL, download the recipe using
    Paprika's built-in scraper, and save it. Optionally adds categories.

    Args:
        url: The recipe URL to import.
        categories: Optional list of category names to tag the recipe with.
            Must match existing categories (case-insensitive).
        page_load_timeout: Seconds to wait for the page to load (default 8).
    """
    # --- Snapshot existing recipe PKs before importing ---
    conn = _get_db()
    try:
        existing_pks = {
            row[0]
            for row in conn.execute("SELECT Z_PK FROM ZRECIPE").fetchall()
        }
    finally:
        conn.close()

    # --- Run the UI automation ---
    script = _import_recipe_applescript(url, page_load_timeout)
    try:
        _run_applescript(script)
    except RuntimeError as e:
        return json.dumps({"error": f"UI automation failed: {e}"})

    # --- Detect the newly imported recipe ---
    new_recipe = None
    for attempt in range(10):
        time.sleep(1)
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT Z_PK, ZNAME, ZSOURCEURL FROM ZRECIPE WHERE Z_PK NOT IN ({})".format(
                    ",".join(str(pk) for pk in existing_pks) if existing_pks else "0"
                )
            ).fetchall()
            if rows:
                # Pick the highest PK (most recently inserted)
                new_recipe = max(rows, key=lambda r: r["Z_PK"])
                break
        finally:
            conn.close()

    if not new_recipe:
        return json.dumps({
            "error": "No new recipe detected after import. "
            "The URL may not be supported by Paprika's scraper, "
            "or the page may not have loaded in time."
        })

    recipe_id = new_recipe["Z_PK"]
    recipe_name = (new_recipe["ZNAME"] or "").rstrip(".")
    source_url = new_recipe["ZSOURCEURL"] or url

    # --- Add categories if requested ---
    categories_added = []
    categories_not_found = []

    if categories:
        _kill_paprika()

        conn = _get_db(read_only=False)
        try:
            cursor = conn.cursor()

            # Resolve category names to PKs
            all_cats = cursor.execute(
                "SELECT Z_PK, ZNAME FROM ZRECIPECATEGORY"
            ).fetchall()
            cat_lookup = {row["ZNAME"].lower(): row for row in all_cats}

            for cat_name in categories:
                match = cat_lookup.get(cat_name.lower())
                if not match:
                    categories_not_found.append(cat_name)
                    continue

                cat_pk = match["Z_PK"]

                # Check if already linked
                already = cursor.execute(
                    "SELECT 1 FROM Z_12CATEGORIES WHERE Z_12RECIPES = ? AND Z_13CATEGORIES = ?",
                    (recipe_id, cat_pk),
                ).fetchone()
                if already:
                    categories_added.append(match["ZNAME"])
                    continue

                # Link recipe to category
                cursor.execute(
                    "INSERT INTO Z_12CATEGORIES (Z_12RECIPES, Z_13CATEGORIES) VALUES (?, ?)",
                    (recipe_id, cat_pk),
                )
                categories_added.append(match["ZNAME"])

            # Mark recipe as needing sync
            if categories_added:
                cursor.execute(
                    """
                    UPDATE ZRECIPE
                    SET Z_OPT = Z_OPT + 1, ZISSYNCED = 0,
                        ZSTATUS = 'modified', ZSYNCHASH = ?
                    WHERE Z_PK = ?
                    """,
                    (_new_sync_hash(), recipe_id),
                )

            conn.commit()
        finally:
            conn.close()

        _open_paprika()

    result = {
        "recipe_id": recipe_id,
        "recipe_name": recipe_name,
        "source_url": source_url,
        "categories_added": categories_added,
        "categories_not_found": categories_not_found,
    }
    return json.dumps(result, indent=2)


# --- Entry point ---

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
