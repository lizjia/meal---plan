from flask import Flask, render_template, request, jsonify
from typing import List, Dict
from dotenv import load_dotenv
import re
import random
import json
import os
import requests

load_dotenv()

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    goals = data.get("goals", {})
    inventory = data.get("inventory", [])

    if inventory:
        for item in inventory:
            if "category" not in item:
                item["category"] = "staple" if item.get("is_staple") else "fridge"
        fridge = [i for i in inventory if i.get("category") == "fridge"]
        condiments = [i for i in inventory if i.get("category") in {"staple", "pantry"}]
    else:
        fridge = data.get("fridge", [])
        condiments = data.get("condiments", [])

    meal_days = max(1, min(int(data.get("days", 7)), 14))
    variation = parse_int(data.get("variation"), 0)

    try:
        result = build_local_plan(goals, fridge, condiments, meal_days, variation)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def parse_int(value, default=0):
    try:
        return int(value) if value not in (None, "") else default
    except (ValueError, TypeError):
        return default


# ── INGREDIENT MATCHING ──────────────────────────────────────────────────────

ALIASES = {
    "bread": ["whole grain bread", "toast", "whole wheat bread"],
    "salmon": ["salmon fillet"],
    "egg": ["eggs"],
    "yogurt": ["greek yogurt"],
    "potato": ["potatoes"],
    "bean": ["beans"],
    "tomato": ["crushed tomatoes", "tomatoes"],
    "broccoli": ["mixed vegetables"],
}

STOPWORDS = {
    "and", "the", "with", "for", "that", "this", "love", "like", "want",
    "quick", "easy", "meal", "meals", "food", "foods", "from", "your", "mine",
    "have", "using", "use", "prefer", "preferences", "please", "only"
}

CUISINE_KEYWORDS = {
    "korean": ["korean", "kimchi", "gochujang", "bulgogi", "bibimbap"],
    "japanese": ["japanese", "teriyaki", "miso", "udon", "ramen", "sushi", "yakitori"],
    "chinese": ["chinese", "stir fry", "szechuan", "kung pao", "lo mein", "fried rice"],
    "indian": ["indian", "curry", "masala", "tikka", "dal", "paneer"],
    "mexican": ["mexican", "taco", "burrito", "fajita", "quesadilla", "enchiladas"],
    "american": ["american", "burger", "bbq", "sandwich", "mac and cheese"],
    "italian": ["italian", "pasta", "marinara", "risotto", "parmesan"],
    "thai": ["thai", "pad thai", "coconut curry", "basil chicken"],
    "mediterranean": ["mediterranean", "hummus", "tzatziki", "shawarma"],
    "french": ["french", "provencal", "ratatouille"],
    "spanish": ["spanish", "paella", "patatas bravas"],
    "greek": ["greek", "feta", "gyros", "moussaka", "souvlaki"],
    "turkish": ["turkish", "kebab", "mezze"],
    "middle-eastern": ["middle eastern", "lebanese", "persian", "shawarma", "falafel"],
    "vietnamese": ["vietnamese", "pho", "banh mi", "lemongrass"],
    "filipino": ["filipino", "adobo", "tocino"],
    "caribbean": ["caribbean", "jamaican", "cuban", "jerk"],
    "brazilian": ["brazilian", "feijoada", "churrasco"],
    "peruvian": ["peruvian", "aji", "lomo saltado"],
    "african": ["african", "moroccan", "ethiopian", "tagine"],
    "vegan": ["vegan", "plant-based"],
    "vegetarian": ["vegetarian"],
    "pescatarian": ["pescatarian"],
    "keto": ["keto"],
    "low-carb": ["low carb", "low-carb"],
    "paleo": ["paleo"],
    "gluten-free": ["gluten free", "gluten-free"],
    "dairy-free": ["dairy free", "dairy-free"],
    "high-protein": ["high protein", "fitness", "gym"],
    "low-calorie": ["low calorie", "weight loss", "cut"],
    "fried foods": ["fried", "crispy", "deep fry", "breaded"],
    "no oil": ["no oil", "oil free", "without oil"],
}

HARD_RESTRICTIONS = {
    "fish": ["fish", "salmon", "tuna", "cod", "tilapia", "anchovy", "sardine", "seafood", "shrimp", "prawn", "crab", "lobster"],
    "dairy": ["dairy", "milk", "cheese", "yogurt", "butter", "cream", "ghee", "paneer", "whey"],
    "peanuts": ["peanut", "peanuts", "groundnut"],
    "tree nuts": ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut", "macadamia", "nuts"],
    "gluten": ["gluten", "wheat", "barley", "rye", "bread", "pasta", "flour", "soy sauce"],
    "soy": ["soy", "soy sauce", "tofu", "tempeh", "edamame"],
    "egg": ["egg", "eggs", "mayonnaise"],
    "shellfish": ["shrimp", "prawn", "crab", "lobster", "shellfish"],
    "sesame": ["sesame", "tahini"],
}


def normalize_food_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower()).strip()
    words = [w for w in cleaned.split() if w not in {"fresh", "raw", "organic"}]
    if not words:
        return ""
    singularized = []
    for word in words:
        if word.endswith("ies"):
            singularized.append(word[:-3] + "y")
        elif word.endswith("s") and len(word) > 3:
            singularized.append(word[:-1])
        else:
            singularized.append(word)
    return " ".join(singularized)


def fuzzy_match(a: str, b: str) -> bool:
    na, nb = normalize_food_name(a), normalize_food_name(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    alias_pool_a, alias_pool_b = [na], [nb]
    for key, vals in ALIASES.items():
        norm_vals = [normalize_food_name(v) for v in vals]
        norm_key = normalize_food_name(key)
        if na == norm_key or na in norm_vals:
            alias_pool_a += [norm_key] + norm_vals
        if nb == norm_key or nb in norm_vals:
            alias_pool_b += [norm_key] + norm_vals
    return any(x == y or x in y or y in x for x in alias_pool_a for y in alias_pool_b)


def extract_preference_keywords(text: str) -> List[str]:
    keywords = []
    for w in re.findall(r"[a-zA-Z]+", (text or "").lower()):
        if len(w) >= 4 and w not in STOPWORDS:
            n = normalize_food_name(w)
            if n and n not in keywords:
                keywords.append(n)
    return keywords[:20]


def extract_banned_terms(restrictions_text: str) -> List[str]:
    text = (restrictions_text or "").lower()
    banned = set()
    for restriction, terms in HARD_RESTRICTIONS.items():
        if restriction in text or f"{restriction}-free" in text or f"no {restriction}" in text:
            banned.update(terms)
    return sorted(banned)


def matches_cuisine(template: Dict, cuisine: str) -> bool:
    searchable = " ".join([template["name"].lower(), " ".join(template["tags"]).lower()])
    return any(k in searchable for k in CUISINE_KEYWORDS.get(cuisine, []))


# ── AI MEAL GENERATION ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a meal planning assistant. Given a list of fridge ingredients, pantry staples, dietary objective, and cuisine/diet preferences, generate exactly 20 meal recommendations covering all meal types.

Return ONLY a valid JSON array with no preamble, markdown, or explanation. Each object must have:
- "name": string — a clear, recognisable dish name. Never invent fictional fusion names.
- "description": string — one sentence describing what the dish is and how it tastes.
- "meal_type": one of "breakfast", "lunch_dinner", "snack", "coffee"
- "tags": string[] of key ingredients used
- "macros": { "cal": int, "protein": int, "carbs": int, "fat": int }
- "missing": string[] of ingredients needed but NOT in the provided fridge/pantry list
- "recipe_url": string (allrecipes.com search URL)
- "image_url": string (leave as empty string "")
- "steps": string[] — 3 to 4 concise cooking steps specific to this dish. Must match the actual dish.

Rules:
- Include at least 3 breakfast, 10 lunch_dinner, 3 snack, and 2 coffee meals
- Prioritize recipes using the most available ingredients
- "missing" must only list items genuinely absent from the provided inventory
- CUISINE PREFERENCES apply ONLY to lunch_dinner meals. Breakfast, snack, and coffee must always be conventional (oatmeal, eggs, yogurt bowl, cold brew etc). Never apply a cuisine style to breakfast or snacks.
- Meal names must be real, well-known dishes. Never combine unrelated cuisine labels with meal types.
- Vary cuisines and styles across lunch_dinner slots only
- Honor dietary preferences and restrictions strictly
- Return ONLY the JSON array"""

FALLBACK_IMAGES = {
    "breakfast":    "https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=400&h=280&fit=crop",
    "lunch_dinner": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400&h=280&fit=crop",
    "snack":        "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=400&h=280&fit=crop",
    "coffee":       "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=400&h=280&fit=crop",
}


def fetch_meal_image(meal_name: str, meal_type: str) -> str:
    cleaned = re.sub(r"\w+-style\s*", "", meal_name, flags=re.IGNORECASE).strip()
    query = " ".join(cleaned.split()[:3])
    try:
        resp = requests.get(
            f"https://www.themealdb.com/api/json/v1/1/search.php?s={requests.utils.quote(query)}",
            timeout=5,
        )
        meals = resp.json().get("meals")
        if meals:
            return meals[0]["strMealThumb"]
    except Exception:
        pass
    return FALLBACK_IMAGES.get(meal_type, FALLBACK_IMAGES["lunch_dinner"])


def fetch_ai_templates(fridge_names, condiment_names, objective, preference_keywords, preferred_cuisines) -> List[Dict]:
    user_prompt = (
        f"Fridge: {fridge_names}\n"
        f"Pantry/staples: {condiment_names}\n"
        f"Objective: {objective}\n"
        f"Preferences: {preference_keywords}\n"
        f"Cuisines: {preferred_cuisines}\n\n"
        "Generate 20 meal recommendations as a JSON array."
    )
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": 4000,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=30,
        )
        raw = response.json()["choices"][0]["message"]["content"]
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        templates = json.loads(raw)
        for t in templates:
            t.setdefault("description", "")
            t.setdefault("steps", [])
            t["image_url"] = fetch_meal_image(t.get("name", ""), t.get("meal_type", "lunch_dinner"))
        return templates
    except Exception as e:
        print(f"[fetch_ai_templates] Groq error: {e}")
        return []


# ── FALLBACK STEPS (used only if AI returns none) ─────────────────────────────

def build_quick_steps(meal_type: str, used_items: List[str], needed_items: List[str]) -> List[str]:
    base = ", ".join((used_items[:3] or needed_items[:3] or ["your ingredients"]))
    if meal_type == "breakfast":
        return [
            f"Prep: {base}.",
            "Cook or assemble in one bowl or pan.",
            "Adjust portion to your macro target.",
        ]
    if meal_type == "snack":
        return [
            f"Portion out: {base}.",
            "Keep prep under 5 minutes.",
            "Pair with water or tea.",
        ]
    if meal_type == "coffee":
        return [
            "Brew coffee (hot or iced).",
            "Add milk or protein add-ins to hit your macro target.",
        ]
    return [
        f"Prep and chop: {base}.",
        "Cook protein first, then add vegetables and carbs.",
        "Batch extra portions for faster weekday meals.",
    ]


# ── PLAN BUILDER ──────────────────────────────────────────────────────────────

def build_local_plan(goals, fridge, condiments, meal_days, variation=0):
    objective = (goals.get("objective") or "eat healthier").lower()
    fridge_names = [str(item.get("name", "")).lower() for item in fridge]
    condiment_names = [str(item.get("name", "")).lower() for item in condiments]
    inventory_all = fridge_names + condiment_names

    preference_keywords = extract_preference_keywords(str(goals.get("preferences", "") or ""))
    selected_cuisines = goals.get("cuisines") or []
    preferred_cuisines = [c for c in selected_cuisines if c in CUISINE_KEYWORDS]
    preference_keywords += preferred_cuisines
    selected_set = set(preferred_cuisines)

    templates = fetch_ai_templates(fridge_names, condiment_names, objective, preference_keywords, preferred_cuisines)
    if not templates:
        raise ValueError("Could not generate meal plan. Please check your API key and try again.")

    # Apply dietary restrictions
    banned_terms = extract_banned_terms(str(goals.get("restrictions", "") or ""))
    if "gluten-free" in selected_set:
        banned_terms.extend(HARD_RESTRICTIONS["gluten"])
    if "dairy-free" in selected_set:
        banned_terms.extend(HARD_RESTRICTIONS["dairy"])
    if "vegan" in selected_set:
        banned_terms.extend(["chicken", "beef", "pork", "fish", "egg", "milk", "cheese", "yogurt", "butter", "honey", "salmon", "turkey"])
    elif "vegetarian" in selected_set:
        banned_terms.extend(["chicken", "beef", "pork", "turkey", "sausage", "fish", "salmon", "tuna", "shrimp"])
    elif "pescatarian" in selected_set:
        banned_terms.extend(["chicken", "beef", "pork", "turkey", "sausage"])

    if banned_terms:
        templates = [
            t for t in templates
            if not any(
                term in " ".join([t["name"].lower(), " ".join(t["tags"]).lower(), " ".join(t["missing"]).lower()])
                for term in banned_terms
            )
        ]
        if not templates:
            raise ValueError("All meals were filtered out by restrictions. Try relaxing restrictions or adding more foods.")

    # Slot setup
    meals_per_day = str(goals.get("meals_per_day") or "3")
    if meals_per_day.startswith("2"):
        base_slots = ["Breakfast", "Dinner"]
    elif meals_per_day.startswith("5"):
        base_slots = ["Breakfast", "Snack", "Lunch", "Snack 2", "Dinner"]
    else:
        base_slots = ["Breakfast", "Lunch", "Dinner"]
    slots = base_slots + ["Coffee", "Snack"]

    randomizer = random.Random(variation + len(fridge_names) * 17 + meal_days)
    unmatched_inventory = set(n for n in fridge_names if n)
    used_recently = []

    def template_fit_score(template, slot_name):
        type_map = {"Breakfast": "breakfast", "Coffee": "coffee", "Snack": "snack", "Snack 2": "snack"}
        needed_type = type_map.get(slot_name, "lunch_dinner")
        if template.get("meal_type") != needed_type:
            return -999

        matched_tags = [t for t in template["tags"] if any(fuzzy_match(inv, t) for inv in fridge_names)]
        new_matches = [inv for inv in unmatched_inventory if any(fuzzy_match(inv, t) for t in template["tags"])]
        missing_penalty = sum(
            1 for m in template["missing"]
            if not any(fuzzy_match(ex, m) for ex in inventory_all)
        )
        if needed_type == "snack" and missing_penalty > 0:
            return -999

        macros = template.get("macros", {})
        carbs, cal, protein = macros.get("carbs", 0), macros.get("cal", 0), macros.get("protein", 0)
        tag_text = " ".join(template["tags"]).lower()
        diet_bonus = 0

        if "keto" in selected_set and carbs > 35: return -999
        if "low-carb" in selected_set and carbs > 55: return -999
        if "low-calorie" in selected_set and cal > 620: return -999
        if "no oil" in selected_set and any(k in tag_text for k in ["fried", "crispy", "deep fry"]): return -999
        if "high-protein" in selected_set and protein >= 30: diet_bonus += 8
        if "fried foods" in selected_set and any(k in tag_text for k in ["fried", "crispy"]): diet_bonus += 10

        repeat_penalty = 3 if template["name"] in used_recently[-4:] else 0
        preference_boost = sum(
            6 for kw in preference_keywords
            if kw and (kw in " ".join([template["name"].lower(), " ".join(template["tags"]).lower()])
                       or any(fuzzy_match(kw, t) for t in template["tags"]))
        )
        cuisine_boost = sum(16 for c in preferred_cuisines if matches_cuisine(template, c))

        return (len(new_matches) * 9) + (len(matched_tags) * 5) + preference_boost + cuisine_boost + diet_bonus - (missing_penalty * 2) - repeat_penalty

    days_structured = []
    grocery_needed = {}
    day_cuisine_hits = {c: 0 for c in preferred_cuisines}

    for day in range(1, meal_days + 1):
        day_totals = {"cal": 0, "protein": 0, "carbs": 0, "fat": 0}
        day_meals = []

        for i, slot in enumerate(slots):
            ranked = sorted(templates, key=lambda t: template_fit_score(t, slot), reverse=True)

            # Prioritise cuisine variety for lunch/dinner
            if preferred_cuisines and slot in {"Lunch", "Dinner"}:
                for cuisine in preferred_cuisines:
                    if day_cuisine_hits.get(cuisine, 0) == 0:
                        forced = [t for t in ranked if matches_cuisine(t, cuisine)]
                        if forced:
                            ranked = forced + [t for t in ranked if t not in forced]
                            break

            top_pool = [m for m in ranked[:max(3, min(6, len(ranked)))] if template_fit_score(m, slot) > -500]

            # Pantry snack fallback
            if not top_pool and slot in {"Snack", "Snack 2"}:
                candidates = [n for n in inventory_all if n]
                if candidates:
                    item = randomizer.choice(candidates)
                    top_pool = [{
                        "name": f"Quick {item.title()} Snack",
                        "description": "",
                        "meal_type": "snack",
                        "tags": [item],
                        "macros": {"cal": 180, "protein": 6, "carbs": 22, "fat": 7},
                        "missing": [],
                        "recipe_url": "https://www.allrecipes.com/search?q=healthy+snack",
                        "image_url": FALLBACK_IMAGES["snack"],
                        "steps": [],
                    }]
            if not top_pool:
                continue

            pool_sorted = sorted(top_pool, key=lambda t: template_fit_score(t, slot), reverse=True)
            selector = (variation * 7 + day * 3 + i) % len(pool_sorted)
            meal = pool_sorted[selector]
            if randomizer.random() > 0.55 and len(pool_sorted) > 1:
                meal = pool_sorted[(selector + randomizer.randint(1, len(pool_sorted) - 1)) % len(pool_sorted)]

            used_recently.append(meal["name"])
            for cuisine in preferred_cuisines:
                if matches_cuisine(meal, cuisine):
                    day_cuisine_hits[cuisine] = 1

            used_items = sorted({
                inv for inv in fridge_names
                if any(fuzzy_match(inv, tag) for tag in meal["tags"] + meal["missing"])
            })
            needed_items = sorted({
                m for m in meal["missing"]
                if not any(fuzzy_match(inv, m) for inv in inventory_all)
            })
            steps = meal.get("steps") or build_quick_steps(meal.get("meal_type", "lunch_dinner"), used_items, needed_items)

            day_meals.append({
                "slot": slot,
                "name": meal["name"],
                "description": meal.get("description", ""),
                "meal_type": meal.get("meal_type", "lunch_dinner"),
                "macros": meal["macros"],
                "recipe_url": meal["recipe_url"],
                "image_url": meal["image_url"],
                "used_inventory": used_items,
                "needed_items": needed_items,
                "quick_steps": steps,
            })

            for k in day_totals:
                day_totals[k] += meal["macros"][k]
            for inv in list(unmatched_inventory):
                if any(fuzzy_match(inv, t) for t in meal["tags"]):
                    unmatched_inventory.discard(inv)
            for missing in meal["missing"]:
                if not any(fuzzy_match(ex, missing) for ex in inventory_all):
                    grocery_needed[missing] = grocery_needed.get(missing, 0) + 1

        days_structured.append({"day": day, "meals": day_meals, "subtotal": day_totals})

    grocery_list = [
        {"name": item, "count": count}
        for item, count in sorted(grocery_needed.items(), key=lambda x: x[1], reverse=True)
    ]
    sunday_prep = {
        "title": f"{templates[0]['name']} + {templates[1]['name'] if len(templates) > 1 else templates[0]['name']}",
        "notes": [
            "Cook 6–8 portions on Sunday, refrigerate for 3 days, freeze the rest.",
            "Prep one protein base, one carb base, and two vegetables for flexible mixing.",
        ],
    }

    return {
        "days": days_structured,
        "grocery_list": grocery_list,
        "sunday_prep": sunday_prep,
    }


if __name__ == "__main__":
    app.run(debug=True, port=5000)