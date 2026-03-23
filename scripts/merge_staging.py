#!/usr/bin/env python3
"""Merge the 4 batch staging files into a single category_staging.json."""

import json
import os
import time
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

BATCH_FILES = [
    os.path.join(DATA_DIR, f"staging_batch_{i}.json")
    for i in range(1, 5)
]
OUTPUT_PATH = os.path.join(DATA_DIR, "category_staging.json")


def main():
    all_changes = []
    for path in BATCH_FILES:
        if not os.path.exists(path):
            print(f"WARNING: {os.path.basename(path)} not found, skipping")
            continue
        with open(path) as f:
            batch = json.load(f)
        print(f"  {os.path.basename(path)}: {len(batch)} recipes with changes")
        all_changes.extend(batch)

    # Deduplicate by recipe ID (in case of overlap)
    seen_ids = set()
    deduped = []
    for change in all_changes:
        rid = change["id"]
        if rid not in seen_ids:
            seen_ids.add(rid)
            deduped.append(change)

    # Sort by recipe name for easy review
    deduped.sort(key=lambda x: x["name"].lower())

    # Build summary
    add_counts = defaultdict(int)
    remove_counts = defaultdict(int)
    for r in deduped:
        for c in r.get("add", []):
            add_counts[c] += 1
        for c in r.get("remove", []):
            remove_counts[c] += 1

    staging = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_recipes_with_changes": len(deduped),
        "summary": {
            "additions_by_category": dict(sorted(add_counts.items(), key=lambda x: -x[1])),
            "removals_by_category": dict(sorted(remove_counts.items(), key=lambda x: -x[1])),
        },
        "changes": deduped,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(staging, f, indent=2)

    print(f"\n=== MERGED ===")
    print(f"Total recipes with changes: {len(deduped)}")
    print(f"\nTop additions:")
    for cat, count in sorted(add_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  +{cat}: {count} recipes")
    if remove_counts:
        print(f"\nTop removals:")
        for cat, count in sorted(remove_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  -{cat}: {count} recipes")
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
