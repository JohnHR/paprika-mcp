# Plan: `import_recipe` MCP Tool via AppleScript UI Automation

## Goal
Add an `import_recipe(url, categories)` tool to `server.py` that automates Paprika's built-in browser to scrape a recipe from a URL and save it, optionally tagging it with categories.

## UI Flow (from screenshots)

1. Click **"Browser"** in the left sidebar
2. Click the **address bar** at the top center
3. **Cmd+A** to select all, then **type the URL**, then **Enter**
4. Wait for the page to load
5. Click **"Download"** button (bottom-right corner of the browser toolbar)
6. Wait for the recipe edit/save view to appear
7. Click **"Save"** button (bottom-right corner of the edit view)
8. After save, add categories via direct DB writes (existing proven pattern)

## Implementation Steps

### Step 1: Explore the accessibility tree

Before writing the automation, run targeted `osascript` commands to discover the exact element paths for:
- The "Browser" sidebar item
- The address bar text field
- The "Download" button
- The "Save" button in the edit view

This is necessary because System Events needs precise element references (e.g., `button "Download" of group 1 of splitter group 1 of window 1`).

### Step 2: Build the AppleScript automation

Write an AppleScript (invoked via `subprocess.run(["osascript", "-e", ...])`) that:
1. Activates Paprika (`activate application "Paprika Recipe Manager 3"`)
2. Clicks "Browser" in the sidebar
3. Clicks the address bar, selects all, types the URL, presses Enter
4. Waits for the page to load (delay ~5-8 seconds, configurable)
5. Clicks "Download"
6. Waits for the recipe edit view (~3 seconds)
7. Clicks "Save"

The URL will be passed as a parameter to the AppleScript.

### Step 3: Detect the newly imported recipe

**Before** running the AppleScript:
- Snapshot all existing recipe `Z_PK` values from the DB (read-only, Paprika stays running)

**After** the AppleScript completes:
- Poll the DB (with retries) for any new `Z_PK` not in the snapshot
- This reliably identifies the recipe Paprika just saved
- Extract the recipe name and details for the return value

### Step 4: Add categories (if requested)

If `categories` is non-empty:
- Resolve each category name to its `Z_PK` (case-insensitive match)
- Use the existing kill → DB write → restart pattern:
  - `_kill_paprika()`
  - INSERT into `Z_12CATEGORIES` join table for each category
  - Mark the recipe as modified for sync (`ZISSYNCED=0`, `ZSTATUS='modified'`, new `ZSYNCHASH`)
  - `_open_paprika()`
- If a category name doesn't exist, report it as unmatched (don't create new categories automatically)

### Step 5: Return result

Return JSON with:
- `recipe_id` (Z_PK)
- `recipe_name`
- `source_url`
- `categories_added` (list of names successfully linked)
- `categories_not_found` (list of names that didn't match any existing category)

## File Changes

**`server.py`** — All changes in this one file:
1. Add a `_run_applescript(script: str) -> str` helper that calls `osascript` via subprocess
2. Add the `_import_recipe_applescript(url: str) -> str` helper that builds the AppleScript string
3. Add the `@mcp.tool() import_recipe(url, categories)` tool function

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Accessibility tree element paths vary by Paprika version | Step 1 exploration; keep element references in named constants for easy updates |
| Page load time varies | Use a generous default delay (8s), with a `page_load_timeout` parameter |
| Download fails (unsupported site) | Poll for new recipe with timeout; return clear error if no recipe appears |
| Paprika not running | Explicitly `open -a` before starting the flow |
| Address bar not focused properly | Use Cmd+L (standard "focus address bar" shortcut) as fallback |
| Recipe edit view doesn't appear after Download | Poll with delay and retry; timeout after ~15s |

## Tool Signature

```python
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
```
