#!/usr/bin/env python3
"""
LLM-powered recipe categorization pipeline.

Reads all recipes from Paprika, sends them to Claude in batches,
and writes suggested category changes to a staging file for review.
"""

import asyncio
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict

import anthropic

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/"
    "72KVKW69K8.com.hindsightlabs.paprika.mac.v3/"
    "Data/Database/Paprika.sqlite"
)
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DEFINITIONS_PATH = os.path.join(DATA_DIR, "category_definitions.json")
STAGING_PATH = os.path.join(DATA_DIR, "category_staging.json")

# Batch size: how many recipes to send per LLM call
BATCH_SIZE = 15
MODEL = "claude-sonnet-4-20250514"
MAX_CONCURRENT = 5


def load_category_definitions():
    with open(DEFINITIONS_PATH) as f:
        return json.load(f)


def load_recipes():
    """Load all active recipes from the database."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    recipes_raw = conn.execute("""
        SELECT Z_PK, ZNAME, ZSOURCEURL, ZRATING, ZONFAVORITES,
               ZPREPTIME, ZCOOKTIME, ZTOTALTIME, ZSERVINGS,
               ZINGREDIENTS, ZDIRECTIONS, ZNOTES
        FROM ZRECIPE
        WHERE ZINTRASH = 0
        ORDER BY ZNAME COLLATE NOCASE
    """).fetchall()

    # Get all categories (non-date-based, non-zz, non-deleted)
    all_categories = conn.execute("""
        SELECT Z_PK, ZNAME FROM ZRECIPECATEGORY
        WHERE ZNAME NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*'
          AND ZNAME NOT LIKE 'zz%'
          AND (ZSTATUS IS NULL OR ZSTATUS != 'deleted')
    """).fetchall()
    cat_map = {row["Z_PK"]: row["ZNAME"] for row in all_categories}

    # Get all recipe-category associations
    assocs = conn.execute("SELECT Z_12RECIPES, Z_13CATEGORIES FROM Z_12CATEGORIES").fetchall()
    recipe_cats = defaultdict(list)
    for a in assocs:
        cat_name = cat_map.get(a["Z_13CATEGORIES"])
        if cat_name:
            recipe_cats[a["Z_12RECIPES"]].append(cat_name)

    recipes = []
    for r in recipes_raw:
        pk = r["Z_PK"]
        recipes.append({
            "id": pk,
            "name": r["ZNAME"],
            "source_url": r["ZSOURCEURL"] or "",
            "rating": r["ZRATING"] or 0,
            "on_favorites": bool(r["ZONFAVORITES"]),
            "prep_time": r["ZPREPTIME"] or "",
            "cook_time": r["ZCOOKTIME"] or "",
            "total_time": r["ZTOTALTIME"] or "",
            "servings": r["ZSERVINGS"] or "",
            "categories": sorted(recipe_cats.get(pk, [])),
            "ingredients": (r["ZINGREDIENTS"] or "")[:1500],  # Truncate long ingredient lists
            "directions": (r["ZDIRECTIONS"] or "")[:1000],    # Truncate long directions
            "notes": (r["ZNOTES"] or "")[:500],               # Truncate long notes
        })

    conn.close()
    return recipes


def build_system_prompt(definitions):
    """Build the system prompt with category definitions."""
    cats = definitions["assignable_categories"]
    skip = definitions["skip_categories"]
    notes = definitions["notes"]

    cat_descriptions = []
    for name, info in cats.items():
        cat_descriptions.append(f"- **{name}**: {info['definition']}")

    skip_descriptions = []
    for name, reason in skip.items():
        skip_descriptions.append(f"- **{name}**: {reason}")

    return f"""You are a recipe categorization assistant. You will be given a batch of recipes with their current categories, ingredients, directions, and notes. For each recipe, suggest which categories it should belong to.

## Assignable Categories

{chr(10).join(cat_descriptions)}

## Categories to NEVER assign (user-managed)

{chr(10).join(skip_descriptions)}

## Rules

{chr(10).join(f"- {n}" for n in notes)}

## Your Task

For each recipe, analyze its name, ingredients, directions, cook time, and notes to determine ALL categories it should belong to (from the assignable list only).

Compare your suggestions against the recipe's current categories. Output ONLY the changes needed:
- "add": categories that should be added (not currently assigned)
- "remove": categories that should be removed (currently assigned but don't fit)

If a recipe's current categories are already correct and complete, output an empty changes object for it.

Be thorough but accurate. It's better to miss a borderline category than to add one that doesn't fit.

For seasonal categories, only assign if the recipe strongly evokes that season (not just because an ingredient happens to be available then).

Respond with a JSON array. Each element must have:
- "id": the recipe ID (integer)
- "name": the recipe name (string, for readability)
- "add": list of category names to add (may be empty)
- "remove": list of category names to remove (may be empty)
- "reasoning": very brief (1 sentence) explanation of key changes, or "no changes" if none

Respond with ONLY the JSON array, no markdown fences or other text."""


def format_recipe_for_prompt(recipe):
    """Format a single recipe for the LLM prompt."""
    parts = [f"### Recipe ID: {recipe['id']} — {recipe['name']}"]
    if recipe["categories"]:
        parts.append(f"Current categories: {', '.join(recipe['categories'])}")
    else:
        parts.append("Current categories: (none)")
    if recipe["ingredients"]:
        parts.append(f"Ingredients:\n{recipe['ingredients']}")
    if recipe["directions"]:
        parts.append(f"Directions:\n{recipe['directions']}")
    if recipe["cook_time"] or recipe["prep_time"] or recipe["total_time"]:
        times = []
        if recipe["prep_time"]:
            times.append(f"prep: {recipe['prep_time']}")
        if recipe["cook_time"]:
            times.append(f"cook: {recipe['cook_time']}")
        if recipe["total_time"]:
            times.append(f"total: {recipe['total_time']}")
        parts.append(f"Time: {', '.join(times)}")
    if recipe["servings"]:
        parts.append(f"Servings: {recipe['servings']}")
    if recipe["notes"]:
        parts.append(f"User notes: {recipe['notes']}")
    return "\n".join(parts)


async def process_batch(client, system_prompt, batch, batch_num, total_batches, semaphore):
    """Process a single batch of recipes."""
    async with semaphore:
        user_content = "\n\n---\n\n".join(format_recipe_for_prompt(r) for r in batch)

        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=MODEL,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                )

                text = response.content[0].text.strip()
                # Strip markdown fences if present
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    if text.endswith("```"):
                        text = text[: text.rfind("```")]

                results = json.loads(text)
                print(f"  Batch {batch_num}/{total_batches}: {len(results)} recipes processed")
                return results

            except json.JSONDecodeError as e:
                print(f"  Batch {batch_num}: JSON parse error (attempt {attempt+1}): {e}")
                if attempt == 2:
                    print(f"  Raw response:\n{text[:500]}")
                    return []
            except Exception as e:
                print(f"  Batch {batch_num}: Error (attempt {attempt+1}): {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return []


async def run_pipeline():
    """Main pipeline: load recipes, batch-call LLM, write staging file."""
    print("Loading category definitions...")
    definitions = load_category_definitions()
    assignable = set(definitions["assignable_categories"].keys())

    print("Loading recipes from database...")
    recipes = load_recipes()
    print(f"  {len(recipes)} recipes loaded")

    system_prompt = build_system_prompt(definitions)

    # Split into batches
    batches = [recipes[i : i + BATCH_SIZE] for i in range(0, len(recipes), BATCH_SIZE)]
    total_batches = len(batches)
    print(f"  Split into {total_batches} batches of up to {BATCH_SIZE} recipes")

    client = anthropic.Anthropic()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    print(f"\nProcessing with {MODEL} (max {MAX_CONCURRENT} concurrent)...")
    start = time.time()

    tasks = [
        process_batch(client, system_prompt, batch, i + 1, total_batches, semaphore)
        for i, batch in enumerate(batches)
    ]
    batch_results = await asyncio.gather(*tasks)

    elapsed = time.time() - start
    print(f"\nLLM processing complete in {elapsed:.1f}s")

    # Flatten results and filter to only recipes with actual changes
    all_results = []
    changes_count = 0
    for batch in batch_results:
        for result in batch:
            # Validate category names
            adds = [c for c in result.get("add", []) if c in assignable]
            removes = [c for c in result.get("remove", []) if c in assignable]

            if adds or removes:
                changes_count += 1

            all_results.append({
                "id": result["id"],
                "name": result["name"],
                "add": adds,
                "remove": removes,
                "reasoning": result.get("reasoning", ""),
            })

    # Build staging file
    staging = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "total_recipes": len(recipes),
        "recipes_with_changes": changes_count,
        "recipes_no_changes": len(all_results) - changes_count,
        "summary": {},
        "changes": [r for r in all_results if r["add"] or r["remove"]],
    }

    # Build summary of category additions/removals
    add_counts = defaultdict(int)
    remove_counts = defaultdict(int)
    for r in all_results:
        for c in r["add"]:
            add_counts[c] += 1
        for c in r["remove"]:
            remove_counts[c] += 1

    staging["summary"] = {
        "additions_by_category": dict(sorted(add_counts.items(), key=lambda x: -x[1])),
        "removals_by_category": dict(sorted(remove_counts.items(), key=lambda x: -x[1])),
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STAGING_PATH, "w") as f:
        json.dump(staging, f, indent=2)

    print(f"\n=== RESULTS ===")
    print(f"Total recipes analyzed: {len(all_results)}")
    print(f"Recipes with suggested changes: {changes_count}")
    print(f"Recipes already correct: {len(all_results) - changes_count}")
    print(f"\nTop additions:")
    for cat, count in sorted(add_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  +{cat}: {count} recipes")
    print(f"\nTop removals:")
    for cat, count in sorted(remove_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  -{cat}: {count} recipes")
    print(f"\nStaging file written to: {STAGING_PATH}")
    print("Review the staging file, then run apply_categories.py to apply changes.")


if __name__ == "__main__":
    asyncio.run(run_pipeline())
