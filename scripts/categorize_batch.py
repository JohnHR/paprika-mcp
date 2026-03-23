#!/usr/bin/env python3
"""Categorize recipes in I-P alphabetical range based on updated category definitions."""

import json
import sys
import re

def has_chicken(recipe):
    text = (recipe.get('ingredients', '') + recipe.get('directions', '') + recipe.get('notes', '')).lower()
    return 'chicken' in text

def has_beef_pork_etc(recipe):
    text = (recipe.get('ingredients', '') + recipe.get('directions', '') + recipe.get('notes', '')).lower()
    return any(w in text for w in ['beef', 'pork', 'lamb', 'sausage', 'bacon', 'brisket', 'steak', 'meatball', 'meatloaf', 'pancetta', 'guiness'])

def has_fish(recipe):
    text = (recipe.get('ingredients', '') + recipe.get('directions', '') + recipe.get('notes', '')).lower()
    return any(w in text for w in ['fish', 'shrimp', 'salmon', 'tuna', 'scallops', 'cod', 'halibut', 'anchovy'])

def is_vegetarian(recipe):
    """Substantial vegetarian entree (lunch/dinner), not just any meat-free dish."""
    text = (recipe.get('ingredients', '') + recipe.get('directions', '') + recipe.get('notes', '')).lower()
    name = recipe.get('name', '').lower()

    # Check for meat/fish
    if has_chicken(recipe) or has_beef_pork_etc(recipe) or has_fish(recipe):
        return False

    # Exclude sides, sauces, dips, relishes
    if any(x in name for x in ['side', 'sauce', 'dip', 'relish', 'bread', 'rolls', 'slaw']):
        return False

    # Likely vegetarian entree
    if any(x in text for x in ['pasta', 'rice', 'bean', 'lentil', 'tofu', 'chickpea', 'paneer', 'egg', 'cheese curry']):
        return True

    return False

def is_breakfast(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    return any(x in text for x in ['breakfast', 'brunch', 'egg', 'oat', 'pancake', 'waffle', 'crepe', 'french toast', 'scrambled', 'frittata', 'omelet', 'granola'])

def is_dinner(recipe):
    """Suitable as main course for dinner."""
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    name = recipe.get('name', '').lower()

    # Exclude sides, snacks, drinks, desserts
    if any(x in text for x in ['side', 'drink', 'cocktail', 'mocktail', 'smoothie', 'snack', 'dip']) or any(x in name for x in ['pie', 'cake', 'cookie', 'pudding']):
        return False

    # Should be a main course
    if any(x in text for x in ['pasta', 'chicken', 'beef', 'pork', 'fish', 'shrimp', 'curry', 'stew', 'soup', 'rice', 'casserole', 'bake', 'roast', 'couscous', 'bean']):
        return True

    return False

def is_dessert(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    # Strong signal for dessert
    if any(x in text for x in ['cake', 'pie', 'cookie', 'ice cream', 'pudding', 'mousse', 'tart', 'brownie', 'candy', 'fudge', 'dessert']):
        return True
    # 'chocolate' and 'sweet' alone aren't enough for savory dishes
    return False

def is_drinks(recipe):
    name = recipe.get('name', '').lower()
    text = name + recipe.get('ingredients', '').lower()
    # Strong signals for drinks
    if any(x in name for x in ['cocktail', 'mocktail', 'smoothie', 'lemonade', 'punch', 'coffee', 'tea', 'fog', 'shrub']):
        return True
    return False

def is_snacks(recipe):
    """Small bites, appetizers eaten outside of meals (not side dishes)."""
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()

    # Not a main course
    if any(x in text for x in ['pasta', 'rice', 'chicken', 'beef', 'pork', 'fish', 'entree']):
        return False

    return any(x in text for x in ['snack', 'dip', 'popcorn', 'nuts', 'trail mix', 'appetizer', 'cracker', 'chip', 'bite', 'energy bite'])

def is_baking(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    return any(x in text for x in ['bread', 'pastry', 'cake', 'cookie', 'bake', 'dough', 'yeast', 'flour', 'muffin', 'scone', 'croissant', 'donut'])

def is_cookies(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '')).lower()
    return 'cookie' in text

def is_pasta(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    return any(x in text for x in ['pasta', 'spaghetti', 'penne', 'orzo', 'noodle', 'ramen', 'udon', 'gnocchi', 'linguine'])

def is_salad(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '')).lower()
    return 'salad' in text

def is_sandwich(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    return any(x in text for x in ['sandwich', 'wrap', 'taco', 'burrito', 'toast', 'gyro', 'bread', 'tortilla'])

def is_soup(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    return any(x in text for x in ['soup', 'stew', 'chili', 'broth'])

def is_casserole(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    return any(x in text for x in ['casserole', 'bake', 'gratin'])

def is_sides(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    name = recipe.get('name', '').lower()
    return 'side' in text or any(x in name for x in ['potato', 'vegetable side', 'rice'])

def is_grilling(recipe):
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    return any(x in text for x in ['grill', 'bbq', 'barbecue'])

def is_instant_pot(recipe):
    text = (recipe.get('directions', '').lower())
    return 'instant pot' in text or 'pressure cooker' in text

def is_slow_cooker(recipe):
    text = (recipe.get('directions', '').lower())
    return 'slow cooker' in text or 'crockpot' in text

def is_weekday(recipe):
    """Quick, simple entree suitable for busy weeknight (under 45 min active time)."""
    text = (recipe.get('name', '') + recipe.get('ingredients', '') + recipe.get('directions', '')).lower()
    cook_time = recipe.get('cook_time', 0) or 0
    prep_time = recipe.get('prep_time', 0) or 0

    # Must be substantial entree (main course)
    if not (has_chicken(recipe) or has_beef_pork_etc(recipe) or has_fish(recipe) or is_vegetarian(recipe)):
        return False

    # Should be quick (under 45 min)
    try:
        cook_time = int(cook_time) if cook_time else 0
        prep_time = int(prep_time) if prep_time else 0
        if cook_time and prep_time:
            if prep_time + cook_time > 45:
                return False
    except (ValueError, TypeError):
        pass

    return True

def is_sunday_dish(recipe):
    """Complex, ambitious recipe for special occasion."""
    text = (recipe.get('directions', '').lower())
    cook_time = recipe.get('cook_time', 0) or 0
    prep_time = recipe.get('prep_time', 0) or 0

    # Long total time
    try:
        cook_time = int(cook_time) if cook_time else 0
        prep_time = int(prep_time) if prep_time else 0
        if cook_time and prep_time:
            if prep_time + cook_time >= 120:
                return True
    except (ValueError, TypeError):
        pass

    # Multiple components or advanced techniques
    if any(x in text for x in ['laminated', 'braise', 'multi-step', 'homemade pasta']):
        return True

    return False

def is_entertaining(recipe):
    """Good for hosting guests - impressive, scales well, or has passive cook time."""
    text = (recipe.get('directions', '').lower() + recipe.get('name', '').lower())
    servings = recipe.get('servings', 0) or 0

    # Serves 6+
    try:
        if int(servings) >= 6:
            return True
    except (ValueError, TypeError):
        pass

    if any(x in text for x in ['impressive', 'elegant', 'showy']):
        return True

    return False

def is_cheap_pantry(recipe):
    """Built primarily from inexpensive, commonly stocked ingredients."""
    ingredients = recipe.get('ingredients', '').lower()

    # Core pantry staples
    pantry = ['pasta', 'rice', 'bean', 'lentil', 'canned tomato', 'egg', 'potato', 'onion', 'garlic', 'flour', 'butter', 'cheese']

    # No expensive items
    expensive = ['saffron', 'truffle', 'lobster', 'crab', 'ribeye', 'filet mignon', 'wagyu', 'scallop', 'shrimp']

    has_pantry = sum(1 for p in pantry if p in ingredients)
    has_expensive = any(e in ingredients for e in expensive)

    return has_pantry >= 2 and not has_expensive

def is_spring(recipe):
    name = recipe.get('name', '').lower()
    ingredients = recipe.get('ingredients', '').lower()
    text = name + ingredients
    # Look for spring produce
    if any(x in text for x in ['asparagus', 'pea', 'artichoke', 'strawberry', 'rhubarb']):
        return True
    if 'spring' in name:
        return True
    return False

def is_summer(recipe):
    name = recipe.get('name', '').lower()
    ingredients = recipe.get('ingredients', '').lower()
    text = name + ingredients
    # Look for summer produce
    if any(x in text for x in ['tomato', 'corn', 'peach', 'berry', 'watermelon']):
        return True
    if 'summer' in name or 'grilled' in text:
        return True
    return False

def is_autumn(recipe):
    name = recipe.get('name', '').lower()
    ingredients = recipe.get('ingredients', '').lower()
    text = name + ingredients
    # Look for fall produce
    if any(x in text for x in ['squash', 'pumpkin', 'apple', 'pear']):
        return True
    if 'autumn' in name or 'fall' in name:
        return True
    return False

def is_winter(recipe):
    name = recipe.get('name', '').lower()
    ingredients = recipe.get('ingredients', '').lower()
    text = name + ingredients
    # Look for winter themes
    if any(x in text for x in ['citrus', 'root vegetable']):
        return True
    if 'winter' in name:
        return True
    return False

def main():
    # Load recipes
    with open('/Users/john.rogers/repo/Personal/paprika-mcp/data/recipes_dump.json', 'r') as f:
        all_recipes = json.load(f)

    # Find recipes in I-P range
    i_to_p_recipes = [r for r in all_recipes if r['name'] and r['name'][0].upper() in 'IJKLMNOP']
    i_to_p_recipes.sort(key=lambda x: x['name'].lower())

    # Analyze each recipe
    results = []
    for recipe in i_to_p_recipes:
        recipe_id = recipe.get('id')
        name = recipe.get('name', '')
        current = recipe.get('categories', [])

        add = []
        remove = []
        reasoning_parts = []

        # Evaluate against all assignable categories
        checks = [
            ('Chicken', has_chicken),
            ('Beef / Pork', has_beef_pork_etc),
            ('Fish', has_fish),
            ('Vegetarian', is_vegetarian),
            ('Breakfast', is_breakfast),
            ('Dinner', is_dinner),
            ('Dessert', is_dessert),
            ('Drinks', is_drinks),
            ('Snacks', is_snacks),
            ('Baking', is_baking),
            ('Cookies', is_cookies),
            ('Pasta', is_pasta),
            ('Salad', is_salad),
            ('Sandwich', is_sandwich),
            ('Soup', is_soup),
            ('Casserole', is_casserole),
            ('Sides', is_sides),
            ('Grilling', is_grilling),
            ('Instant Pot', is_instant_pot),
            ('Slow Cooker', is_slow_cooker),
            ('Weekday', is_weekday),
            ('Sunday Dish', is_sunday_dish),
            ('Entertaining', is_entertaining),
            ('Cheap / Pantry Staples', is_cheap_pantry),
            ('1 - Spring', is_spring),
            ('2- Summer', is_summer),
            ('3 - Autumn', is_autumn),
            ('4 - Winter', is_winter),
        ]

        for cat_name, check_func in checks:
            if check_func(recipe):
                if cat_name not in current:
                    add.append(cat_name)
                    reasoning_parts.append(cat_name)

        reasoning = f"Add: {', '.join(reasoning_parts)}" if reasoning_parts else "No changes needed"

        results.append({
            "id": recipe_id,
            "name": name,
            "current": current,
            "add": add,
            "remove": remove,
            "reasoning": reasoning
        })

    # Write output
    with open('/Users/john.rogers/repo/Personal/paprika-mcp/data/staging_batch_3_v3.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Analyzed {len(results)} recipes")
    print(f"Recipes with changes: {sum(1 for r in results if r['add'] or r['remove'])}")
    print("Output written to staging_batch_3_v3.json")

if __name__ == '__main__':
    main()
