# Paprika MCP Server

An MCP server that lets Claude query and manage your Paprika 3 recipe database for meal planning.

## Tools

### Read Tools
- **browse_recipes** — Page through the full library with configurable sort (name, id, rating, preference_score, last_made, prep_time, cook_time) and pagination (offset/limit)
- **search_recipes** — Search by keyword, category, and minimum preference score (default 4 — pass `min_score=0` to include all recipes). Supports three sort strategies: `score_then_staleness` (default), `staleness` (never-made/oldest first), and `score` (pure favorites)
- **get_recipe_details** — Get full recipe with ingredients and directions; accepts `recipe_id` (exact), `url` (source URL match), or `name` (partial match — returns a disambiguation list if multiple recipes match)
- **get_meal_history** — See what you've cooked recently (based on dated menu categories)
- **list_categories** — List all recipe categories with their IDs
- **get_category_definitions** — Return the full category definitions JSON (names, rules, signals, edge cases) used for classifying recipes

### Write Tools
- **create_meal_plan** — Create a new date-based meal plan by tagging recipes with a category (automatically restarts Paprika)
- **import_recipe** — Import a recipe from a URL using Paprika's built-in browser/scraper (auto-deduplicates)
- **add_recipe_to_category** — Add one or more recipes to an existing category (accepts a single ID or a list for bulk operations)
- **remove_recipe_from_category** — Remove one or more recipes from a category (accepts a single ID or a list for bulk operations)
- **delete_category** — Delete a category and all its recipe associations
- **delete_recipe** — Move a recipe to trash (soft-delete; syncs deletion to other devices and removes all category associations)

### Preference Score (0–7)

Each recipe gets a composite score: star rating (0–5) + 1 if in "Tried and True" + 1 if favorited.

## Setup

### 1. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Add to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "paprika": {
      "command": "uv",
      "args": ["--directory", "/Users/YOUR_USERNAME/Desktop/Claude/paprika-mcp", "run", "server.py"]
    }
  }
}
```

Replace `YOUR_USERNAME` with your macOS username.

### 3. Restart Claude Desktop

The Paprika tools will now be available in any conversation.

## Example prompts

- "Plan 5 dinners — one vegetarian, one fish, and use up the chicken thighs I defrosted."
- "Keep the salmon and butter chicken, but find different veggie and pasta options."
- "I like those but throw in something we've never made before."
- "What are our highest-rated recipes we haven't made in a while?"
- "Show me what we've been eating the last few weeks."
- "Import this recipe: https://example.com/amazing-soup"

## How it works

The server directly accesses the Paprika 3 SQLite database to read recipes and manage meal plans. For imports, it drives Paprika's built-in browser via AppleScript to scrape and save recipes from URLs.

When creating meal plans, it:
1. Creates a new category with format `YYYYMMDD Label` (e.g., "20260215 Menu")
2. Tags the selected recipes with this category
3. Automatically restarts Paprika so the changes are visible immediately

Categories in Paprika work like tags, so recipes can belong to multiple categories/meal plans.

"Last made" dates are inferred from meal plan categories — if a recipe is tagged with "20260309 Menu", it was last made around March 9, 2026.

### Syncing across devices

Write operations (creating meal plans, tagging recipes, importing, deleting categories) mark affected records as dirty (`ZISSYNCED = 0`, `ZSTATUS = 'modified'`/`'new'`/`'deleted'`) with a fresh `ZSYNCHASH`. This tells Paprika's built-in sync engine to push the changes to the cloud on its next sync cycle, so they propagate to other devices automatically.
