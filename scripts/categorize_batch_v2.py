#!/usr/bin/env python3
"""Categorize recipes in I-P alphabetical range based on updated category definitions."""

import json
import re

def normalize_text(text):
    """Normalize text for searching."""
    if not text:
        return ""
    return text.lower().strip()

def search_text(recipe, keywords, field_priority=None):
    """Search for keywords in recipe fields with optional priority."""
    text = ""

    if field_priority:
        # Search priority fields first
        for field in field_priority:
            text += normalize_text(recipe.get(field, "")) + " "
    else:
        # Default: search name, ingredients, directions
        text += normalize_text(recipe.get('name', '')) + " "
        text += normalize_text(recipe.get('ingredients', '')) + " "
        text += normalize_text(recipe.get('directions', '')) + " "

    for keyword in keywords:
        if keyword in text:
            return True
    return False

def has_chicken(recipe):
    """Check if chicken is a primary protein."""
    return search_text(recipe, ['chicken'], ['name', 'ingredients'])

def has_beef_pork_etc(recipe):
    """Check if beef, pork, lamb, etc. is a primary protein."""
    keywords = ['beef', 'pork', 'lamb', 'ground beef', 'steak', 'brisket', 'meatball', 'meatloaf']
    # Don't count bacon if it's just in optional toppings
    text = normalize_text(recipe.get('ingredients', ''))
    if 'bacon' in text and 'optional' not in text:
        keywords.append('bacon')

    return search_text(recipe, keywords, ['name', 'ingredients'])

def has_fish(recipe):
    """Check if fish or seafood is a primary protein."""
    keywords = ['fish', 'salmon', 'tuna', 'halibut', 'cod', 'anchovy']
    # Shrimp is usually a protein in the recipe
    if 'shrimp' in normalize_text(recipe.get('ingredients', '')):
        keywords.append('shrimp')

    return search_text(recipe, keywords, ['name', 'ingredients'])

def is_vegetarian(recipe):
    """Substantial vegetarian entree (lunch/dinner), not just any meat-free dish."""
    # Can't be vegetarian if it has meat
    if has_chicken(recipe) or has_beef_pork_etc(recipe) or has_fish(recipe):
        return False

    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    # Exclude sides, sauces, dips, relishes, breads, etc.
    if any(x in name for x in ['side', 'sauce', 'dip', 'relish', 'bread', 'rolls', 'slaw', 'pudding']):
        return False

    # Must be substantial — look for entree indicators
    entree_indicators = ['pasta', 'rice', 'curry', 'bean', 'lentil', 'tofu', 'chickpea', 'paneer', 'quiche', 'frittata']

    for indicator in entree_indicators:
        if indicator in ingredients or indicator in name:
            return True

    return False

def is_breakfast(recipe):
    """Primarily a breakfast or brunch dish."""
    keywords = ['breakfast', 'brunch', 'pancake', 'waffle', 'crepe', 'french toast', 'granola', 'frittata', 'omelet']
    # Egg is only a breakfast indicator if combined with breakfast terms or egg-specific dishes
    name = normalize_text(recipe.get('name', ''))
    if 'egg' in name and any(x in name for x in ['frittata', 'scrambled', 'hash']):
        keywords.append('egg')

    return search_text(recipe, keywords, ['name'])

def is_dinner(recipe):
    """Suitable as main course for dinner."""
    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    # Exclude things that are clearly not dinner entrees
    if any(x in name for x in ['pie', 'cake', 'cookie', 'pudding', 'side', 'dip', 'cocktail', 'smoothie']):
        return False

    # Must have entree indicators
    entree_keywords = ['chicken', 'beef', 'pork', 'fish', 'shrimp', 'salmon', 'pasta', 'rice', 'curry', 'stew', 'casserole', 'roast', 'bean', 'lentil', 'tofu']

    for keyword in entree_keywords:
        if keyword in ingredients or keyword in name:
            return True

    return False

def is_dessert(recipe):
    """Sweet course served after a meal, or a sweet treat."""
    keywords = ['cake', 'pie', 'cookie', 'ice cream', 'pudding', 'mousse', 'tart', 'brownie', 'candy', 'fudge', 'dessert', 'cupcake']
    return search_text(recipe, keywords, ['name'])

def is_drinks(recipe):
    """Beverages — cocktails, mocktails, coffee drinks, smoothies, etc."""
    keywords = ['cocktail', 'mocktail', 'smoothie', 'lemonade', 'punch', 'shrub']
    # Coffee/tea only if explicitly mentioned in name
    name = normalize_text(recipe.get('name', ''))
    if any(x in name for x in ['coffee', 'tea', 'fog']):
        keywords.extend(['coffee', 'tea', 'fog'])

    return search_text(recipe, keywords, ['name'])

def is_snacks(recipe):
    """Small bites, appetizers eaten outside of meals (not side dishes)."""
    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    # Not a main course
    if any(x in ingredients for x in ['chicken', 'beef', 'pork', 'fish', 'pasta', 'rice']):
        return False

    # Look for snack indicators
    keywords = ['snack', 'dip', 'popcorn', 'nuts', 'trail mix', 'appetizer', 'cracker', 'chip', 'bite', 'energy bite']
    return search_text(recipe, keywords, ['name'])

def is_baking(recipe):
    """Recipes for things you'd find in a bakery — breads, pastries, cakes, cookies."""
    keywords = ['bread', 'pastry', 'cake', 'cookie', 'dough', 'yeast', 'baking powder', 'muffin', 'scone', 'croissant', 'donut', 'biscotti']
    # Exclude savory "baked" items (like baked kebabs, baked fish, etc.)
    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    # Don't match if it's a savory dish with "bake" in the name
    if any(x in name for x in ['kebab', 'fish', 'chicken', 'beef', 'pork']) and 'bake' in name:
        return False

    return search_text(recipe, keywords, ['name', 'ingredients'])

def is_cookies(recipe):
    """Specifically cookies."""
    return 'cookie' in normalize_text(recipe.get('name', ''))

def is_pasta(recipe):
    """Recipe where pasta or noodles are a primary component."""
    keywords = ['pasta', 'spaghetti', 'penne', 'orzo', 'noodle', 'ramen', 'udon', 'gnocchi', 'linguine']
    return search_text(recipe, keywords, ['name', 'ingredients'])

def is_salad(recipe):
    """A salad."""
    return 'salad' in normalize_text(recipe.get('name', ''))

def is_sandwich(recipe):
    """Sandwiches, wraps, tacos, burritos, etc."""
    keywords = ['sandwich', 'wrap', 'taco', 'burrito', 'gyro']
    # Bread only if explicitly indicated (not just in ingredients)
    name = normalize_text(recipe.get('name', ''))
    if any(x in name for x in ['toast', 'bread', 'tortilla']):
        keywords.extend(['toast', 'bread', 'tortilla'])

    return search_text(recipe, keywords, ['name'])

def is_soup(recipe):
    """Soups, stews, chilis, broths."""
    keywords = ['soup', 'stew', 'chili', 'broth']
    return search_text(recipe, keywords, ['name', 'ingredients'])

def is_casserole(recipe):
    """One-dish baked meals, gratins, bakes."""
    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    # Direct match for casserole or gratin
    if 'casserole' in name or 'gratin' in name:
        return True

    # Bakes with ingredients that are typically baked together
    if 'bake' in name or 'baked' in name:
        if any(x in ingredients for x in ['egg', 'frittata', 'chicken', 'beef', 'pasta', 'rice', 'potato']):
            return True

    return False

def is_sides(recipe):
    """Side dishes — vegetables, starches, breads that accompany a main course."""
    name = normalize_text(recipe.get('name', ''))
    return 'side' in name or any(x in name for x in ['potato side', 'vegetable side', 'rice'])

def is_grilling(recipe):
    """Recipe cooked on a grill."""
    keywords = ['grill', 'bbq', 'barbecue']
    return search_text(recipe, keywords, ['name', 'directions'])

def is_instant_pot(recipe):
    """Recipe specifically uses an Instant Pot or pressure cooker."""
    keywords = ['instant pot', 'pressure cooker']
    return search_text(recipe, keywords, ['directions', 'name'])

def is_slow_cooker(recipe):
    """Recipe specifically uses a slow cooker or crockpot."""
    keywords = ['slow cooker', 'crockpot']
    return search_text(recipe, keywords, ['directions', 'name'])

def is_weekday(recipe):
    """Quick, simple entree suitable for busy weeknight (under 45 min active time)."""
    # Must be substantial entree
    if not (has_chicken(recipe) or has_beef_pork_etc(recipe) or has_fish(recipe) or is_vegetarian(recipe)):
        return False

    cook_time = recipe.get('cook_time', 0) or 0
    prep_time = recipe.get('prep_time', 0) or 0

    # Should be quick (under 45 min) - but be lenient if times aren't provided
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
    """Complex, ambitious recipe that's a 'project' for special occasion."""
    cook_time = recipe.get('cook_time', 0) or 0
    prep_time = recipe.get('prep_time', 0) or 0

    # Long total time (2+ hours)
    try:
        cook_time = int(cook_time) if cook_time else 0
        prep_time = int(prep_time) if prep_time else 0
        if cook_time and prep_time:
            if prep_time + cook_time >= 120:
                return True
    except (ValueError, TypeError):
        pass

    return False

def is_entertaining(recipe):
    """Good for hosting guests."""
    servings = recipe.get('servings', 0) or 0

    # Serves 6+
    try:
        if int(servings) >= 6:
            return True
    except (ValueError, TypeError):
        pass

    return False

def is_cheap_pantry(recipe):
    """Built primarily from inexpensive, commonly stocked ingredients."""
    ingredients = normalize_text(recipe.get('ingredients', ''))

    # Core pantry staples
    pantry = ['pasta', 'rice', 'bean', 'lentil', 'canned tomato', 'egg', 'potato', 'onion', 'garlic', 'flour', 'butter', 'cheese']

    # Expensive items
    expensive = ['saffron', 'truffle', 'lobster', 'crab', 'ribeye', 'filet mignon', 'wagyu', 'scallop']

    has_pantry = sum(1 for p in pantry if p in ingredients)
    has_expensive = any(e in ingredients for e in expensive)

    return has_pantry >= 2 and not has_expensive

def is_spring(recipe):
    """Spring recipes with fresh, light produce."""
    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    if 'spring' in name:
        return True

    # Look for spring vegetables (be specific to avoid false positives)
    if 'asparagus' in ingredients or 'artichoke' in ingredients or 'rhubarb' in ingredients:
        return True
    if 'strawberry' in ingredients or 'strawberries' in ingredients:
        return True
    # 'pea' must be fresh pea, not peanut
    if 'fresh pea' in ingredients or ' peas' in ingredients or 'snap pea' in ingredients:
        return True

    return False

def is_summer(recipe):
    """Summer recipes with fresh produce, grilling, cold/light."""
    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    if 'summer' in name:
        return True

    # Look for summer produce
    if any(x in ingredients for x in ['tomato', 'corn', 'peach', 'watermelon']):
        return True
    # Berry is often summer (avoid false positives with 'berry' in other contexts)
    if 'berry' in ingredients or 'blueberry' in ingredients or 'strawberry' in ingredients:
        return True

    # Grilled items are often summer
    if 'grill' in normalize_text(recipe.get('directions', '')):
        return True

    return False

def is_autumn(recipe):
    """Fall recipes with warming, hearty produce."""
    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    if 'autumn' in name or 'fall' in name:
        return True

    # Look for fall produce
    if any(x in ingredients for x in ['squash', 'pumpkin', 'apple', 'pear']):
        return True

    return False

def is_winter(recipe):
    """Winter recipes with heavy, warming comfort food."""
    name = normalize_text(recipe.get('name', ''))
    ingredients = normalize_text(recipe.get('ingredients', ''))

    if 'winter' in name:
        return True

    # Look for winter produce/themes
    if 'citrus' in ingredients or 'root vegetable' in ingredients:
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
            "remove": [],
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
