#!/usr/bin/env python3
"""
Evaluate recipe category assignments using Claude via the Batches API.
Flags entries where the assigned categories seem wrong given the recipe name.

Usage:
    python3 eval_categories.py           # Submit batch + poll until done
    python3 eval_categories.py --resume  # Resume polling a previously submitted batch
"""

import json
import re
import time
import sys
import os
from pathlib import Path

import anthropic

# Load .env if present (overrides any existing env vars)
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

STAGING_FILE   = "data/category_staging_final.json"
BATCH_ID_FILE  = "data/eval_batch_id.txt"
RESULTS_FILE   = "data/eval_flagged.json"

SYSTEM_PROMPT = """You are a recipe category auditor. Given a recipe name and its assigned categories,
identify any OBVIOUS mismatches — cases where a category is clearly wrong for the dish described.

Focus only on clear errors, such as:
- A dessert (cake, cookies, ice cream, etc.) tagged as Dinner, Beef/Pork, Fish, Chicken, or Sandwich
- A beef/pork dish tagged as Fish or Vegetarian
- A chicken dish tagged as Fish, Beef/Pork, or Vegetarian
- A fish/seafood dish tagged as Chicken, Beef/Pork, or Vegetarian
- A breakfast dish tagged as Dinner (unless it's a brunch-style dish)
- Any other obvious mismatch between the dish and its categories

Do NOT flag:
- Edge cases or ambiguous dishes (e.g., savory cakes, brunch items)
- Missing categories (only wrong ones)
- Stylistic disagreements

Respond in JSON with this exact structure:
{
  "flagged": true or false,
  "issues": ["short description of each issue"] or [],
  "confidence": "high" or "medium"
}

Only set flagged=true for clear, obvious errors. When in doubt, set flagged=false."""

def make_prompt(change: dict) -> str:
    effective = sorted(
        (set(change["current_categories"]) - set(change.get("remove", [])))
        | set(change.get("add", []))
    )
    add_str    = ", ".join(change["add"])    if change.get("add")    else "(none)"
    remove_str = ", ".join(change["remove"]) if change.get("remove") else "(none)"

    return f"""Recipe name: {change['name']}

Effective categories after changes: {', '.join(effective) if effective else '(none)'}
  - Adding: {add_str}
  - Removing: {remove_str}
  - Was: {', '.join(change['current_categories']) if change['current_categories'] else '(none)'}

Is this category assignment obviously wrong? Respond in the JSON format specified."""


def submit_batch(client, changes):
    print(f"Building {len(changes)} batch requests...")
    requests = [
        Request(
            custom_id=str(change["id"]),
            params=MessageCreateParamsNonStreaming(
                model="claude-haiku-4-5",
                max_tokens=256,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": make_prompt(change)}],
            ),
        )
        for change in changes
    ]

    print("Submitting batch to Anthropic...")
    batch = client.messages.batches.create(requests=requests)
    print(f"✅ Batch submitted: {batch.id}")
    Path(BATCH_ID_FILE).write_text(batch.id)
    print(f"   Batch ID saved to {BATCH_ID_FILE}")
    return batch.id


def poll_until_done(client, batch_id):
    print(f"\nPolling batch {batch_id}...")
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        print(
            f"  Status: {batch.processing_status} | "
            f"processing={counts.processing} succeeded={counts.succeeded} "
            f"errored={counts.errored} canceled={counts.canceled} expired={counts.expired}"
        )
        if batch.processing_status == "ended":
            print("✅ Batch complete!")
            return batch
        time.sleep(15)


def process_results(client, batch_id, changes_by_id):
    print("\nProcessing results...")
    flagged = []
    errors  = []

    for result in client.messages.batches.results(batch_id):
        recipe_id = int(result.custom_id)
        change    = changes_by_id.get(recipe_id)

        if result.result.type == "succeeded":
            text = next(
                (b.text for b in result.result.message.content if b.type == "text"), ""
            )
            try:
                # Strip markdown code fences if present
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
                json_str = match.group(1) if match else text.strip()
                parsed = json.loads(json_str)
                if parsed.get("flagged") and parsed.get("confidence") in ("high", "medium"):
                    flagged.append({
                        "id":                 recipe_id,
                        "name":               change["name"],
                        "current_categories": change["current_categories"],
                        "add":                change.get("add", []),
                        "remove":             change.get("remove", []),
                        "reasoning":          change.get("reasoning", ""),
                        "eval_issues":        parsed.get("issues", []),
                        "eval_confidence":    parsed.get("confidence"),
                    })
            except json.JSONDecodeError:
                errors.append({"id": recipe_id, "raw": text, "error": "JSON parse failed"})

        elif result.result.type == "errored":
            errors.append({"id": recipe_id, "error": str(result.result.error)})

    return flagged, errors


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in .env or environment")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    with open(STAGING_FILE) as f:
        data = json.load(f)
    changes = data["changes"]
    changes_by_id = {c["id"]: c for c in changes}

    resume = "--resume" in sys.argv
    if resume and Path(BATCH_ID_FILE).exists():
        batch_id = Path(BATCH_ID_FILE).read_text().strip()
        print(f"Resuming batch: {batch_id}")
    else:
        batch_id = submit_batch(client, changes)

    poll_until_done(client, batch_id)
    flagged, errors = process_results(client, batch_id, changes_by_id)

    # Sort by confidence (high first), then name
    flagged.sort(key=lambda x: (x["eval_confidence"] != "high", x["name"]))

    with open(RESULTS_FILE, "w") as f:
        json.dump(flagged, f, indent=2)

    print(f"\n{'='*50}")
    print(f"✅ Flagged {len(flagged)} potentially wrong entries")
    if errors:
        print(f"⚠️  {len(errors)} errors (see below)")
        for e in errors[:5]:
            print(f"   ID {e['id']}: {e.get('error', '')[:80]}")
    print(f"\nResults saved to: {RESULTS_FILE}")
    print(f"\nTop flagged entries:")
    for entry in flagged[:10]:
        print(f"  [{entry['eval_confidence'].upper()}] ID {entry['id']}: {entry['name']}")
        for issue in entry["eval_issues"]:
            print(f"    → {issue}")


if __name__ == "__main__":
    main()
