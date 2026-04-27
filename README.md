# FridgePlan — AI Meal Planner

A fridge-first meal planning app that takes your ingredients and generates a personalised weekly meal plan, grocery list, and Sunday prep guide — powered by AI.

Built in 48 hours as part of a BizOps AI tools assignment.

---

## What it does

- Input what's in your fridge, pantry, and staples
- Set your fitness objective, macro targets, dietary restrictions, and cuisine preferences
- Generate a full meal plan (up to 10 days) with real food photos, macro estimates, cooking steps, and recipe links
- Auto-generate a grocery checklist of only what's missing — tick items off to add them to your inventory
- Sunday prep recommendation built into every plan

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python / Flask | Simple, fast to build, easy to demo locally |
| AI | Groq API (LLaMA 3.3 70B) | Free tier, fast inference, OpenAI-compatible |
| Images | TheMealDB API | Free, no key needed, real food photos |
| Frontend | Vanilla HTML/CSS/JS | No build step, runs anywhere |
| Storage | Browser localStorage | Zero backend complexity for a single-user demo |

---

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/yourusername/meal-plan.git
cd meal-plan
```

**2. Create and activate a virtual environment**
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate
```

**3. Install dependencies**
```bash
pip install flask requests python-dotenv
```

**4. Get a free Groq API key**

Sign up at [console.groq.com](https://console.groq.com) — no credit card required.

**5. Create a `.env` file in the project root**
```
GROQ_API_KEY=your_key_here
```

**6. Run the app**
```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## How it works

1. **Inventory** — user adds fridge items, staples, and pantry items
2. **Goals** — user sets objective (lose weight / gain muscle), macros, cuisine preferences, and dietary restrictions
3. **Generation** — Flask sends a structured prompt to Groq with the full inventory and goals; LLaMA returns 20 meal candidates as JSON
4. **Scoring** — a deterministic scoring function (`template_fit_score`) ranks meals by ingredient match, cuisine fit, macro alignment, and variety
5. **Plan building** — meals are slotted into breakfast/lunch/dinner/snack/coffee across the requested number of days
6. **Images** — Flask queries TheMealDB by meal name to fetch a real food photo; falls back to a type-appropriate Unsplash image
7. **Grocery list** — any ingredient in `missing[]` that isn't already in inventory gets added to the checklist

---

## Key tradeoffs

**Groq + LLaMA over GPT-4/Claude** — free and fast enough for a demo, but less consistent JSON structure. Mitigated by a strict system prompt and JSON parse error handling.

**AI-estimated macros** — no nutrition API needed, but counts are approximations. A production version would call Edamam or Nutritionix for accurate values.

**localStorage over a database** — zero infrastructure, instant persistence, but data is browser and device-specific. Fine for a single-user demo; a real product would need accounts and a database.

**TheMealDB for images** — free, no key, but limited coverage. Anything not in its database falls back to a generic food photo by meal type.

**Flask monolith over API + frontend split** — faster to build and demo, but the right long-term architecture would separate the API from the frontend.

---

## Project structure

```
meal-plan/
├── app.py              # Flask backend — routing, AI calls, plan logic
├── templates/
│   └── index.html      # Single-page frontend
├── .env                # API keys (not committed)
├── .gitignore
└── README.md
```

---

## What's next

- Swap AI macro estimates for a real nutrition API (Edamam free tier)
- User accounts + meal history to personalise recommendations over time
- Feedback loop — track which meals get cooked to improve future scoring
- Mobile app wrapper
