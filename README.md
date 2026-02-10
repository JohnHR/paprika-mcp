# Paprika MCP Server

An MCP server that lets Claude query and manage your Paprika 3 recipe database for meal planning.

## Tools

### Read Tools
- **search_recipes** — Search by keyword, category, and minimum preference score
- **get_recipe_details** — Get full recipe with ingredients and directions
- **get_meal_history** — See what you've cooked recently (based on dated menu categories)

### Write Tools
- **create_meal_plan** — Create a new date-based meal plan by tagging recipes with a category (automatically restarts Paprika)
- **add_recipe_to_category** — Add a recipe to an existing category
- **remove_recipe_from_category** — Remove a recipe from a category
- **delete_category** — Delete a category and all its recipe associations

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

- "Plan 5 dinners for next week — one vegetarian, one fish, and use up the chicken thighs I defrosted."
- "What are our highest-rated recipes we haven't made in a while?"
- "Show me what we've been eating the last few weeks."
- "Create a meal plan for Friday with Chicken Tikka Masala and Garlic Naan"
- "Actually, swap out that recipe for Butter Chicken instead"
- "Add Garlic Naan to tomorrow's dinner plan"
- "Never mind, delete that whole meal plan"

## How it works

The server directly accesses the Paprika 3 SQLite database to read recipes and create meal plans. When creating meal plans, it:
1. Creates a new category with format `YYYYMMDD Label` (e.g., "20260215 Menu")
2. Tags the selected recipes with this category
3. Automatically restarts Paprika so the changes are visible immediately

Categories in Paprika work like tags, so recipes can belong to multiple categories/meal plans.
