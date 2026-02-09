# Paprika MCP Server

A read-only MCP server that lets Claude query your Paprika 3 recipe database for meal planning.

## Tools

- **search_recipes** — Search by keyword, category, and minimum preference score
- **get_recipe_details** — Get full recipe with ingredients and directions
- **get_meal_history** — See what you've cooked recently (based on dated menu categories)

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
