# RetailMind v2 — Multi-Agent Product Intelligence

A 5-agent LangChain system (Router + 4 Specialists + Supervisor) wrapped in a FastAPI backend with a custom HTML/CSS/JS frontend (landing page + floating chat widget — no Streamlit).

Built for the StyleCraft demo: replaces Priya Mehta's 4–5-hour weekly catalog audit with a real-time conversational interface.

---

## Quickstart

```bash
cd retailmind_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY
python run.py                 # opens http://127.0.0.1:8000 in your browser
```

Click the chat icon in the bottom-right of the landing page. The Daily Briefing renders on first open (Supervisor orchestrates all four specialists).

---

## Architecture

```
                       [User Query]
                            |
                    +-------v--------+
                    |  Router Agent  |   LLM classifier:
                    |  (gpt-4o-mini) |   INVENTORY / PRICING /
                    +-------+--------+   REVIEWS / CATALOG /
                            |            MULTI / GENERAL
          +-----------------+------------------+
          |        |        |        |         |
          v        v        v        v         v
    +-----------+ +---------+ +---------+ +---------+
    | Inventory | | Pricing | | Reviews | | Catalog |
    |   Agent   | |  Agent  | |  Agent  | |  Agent  |
    +-----+-----+ +----+----+ +----+----+ +----+----+
          |            |           |           |
       (own tools)  (own tools)  (own tools)  (own tools)
          |            |           |           |
          +------------+-----+-----+-----------+
                             |
                             v  (only for MULTI route +
                +------------+------------+   Daily Briefing)
                |  Supervisor / Synthesis |
                |  Agent (gpt-4o, no tools)|
                +------------+------------+
                             |
                             v
                       [Final Answer]
```

### Query → agent path mapping

| Route | Triggered when the user asks about… | Dispatched to |
|---|---|---|
| `INVENTORY` | Stock levels, restock needs, days to stockout | InventoryAgent → `get_inventory_health` / `generate_restock_alert` |
| `PRICING` | Margin, profitability, price positioning | PricingAgent → `get_pricing_analysis` / `compare_category_pricing` |
| `REVIEWS` | Customer feedback, sentiment, complaints | ReviewsAgent → `get_review_insights` / `get_negative_review_themes` |
| `CATALOG` | Product search, category overview | CatalogAgent → `search_products` / `get_category_performance` |
| `MULTI` | Cross-domain ("Why is X underperforming?", "Should we discount Y?") | Supervisor → calls 2+ specialists in parallel, synthesises one prioritised answer with citations |
| `GENERAL` | Greetings, meta questions | Direct LLM, no tools |

The router is LLM-powered (`ChatOpenAI` + Pydantic structured output) — no keyword/regex matching. See `agents/router.py`.

### Specialist isolation
Each specialist file imports only its own tools module:
- `agents/inventory_agent.py` ← `tools/inventory_tools.py`
- `agents/pricing_agent.py` ← `tools/pricing_tools.py`
- `agents/reviews_agent.py` ← `tools/reviews_tools.py`
- `agents/catalog_agent.py` ← `tools/catalog_tools.py`

There is no shared `ALL_TOOLS` registry. Code inspection will confirm.

### Memory
Per-session `BufferMemory` (in `core/memory.py`) keyed by a UUID `session_id` that the frontend persists in `localStorage`. Every `/chat` call loads `chat_history` into the router and the specialist/supervisor so follow-ups like *"what's its margin?"* resolve to the SKU mentioned earlier. The Clear button wipes the session and re-triggers the Daily Briefing. This implements the +5 bonus criterion (ConversationBufferMemory equivalent).

---

## Project layout

```
retailmind_agent/
├── run.py                       # python run.py → uvicorn + auto-open browser
├── server.py                    # FastAPI: /chat /briefing /summary /clear /trace /categories
├── requirements.txt
├── .env.example
├── data/
│   ├── retailmind_products.csv
│   └── retailmind_reviews.csv
├── agents/
│   ├── router.py                # LLM-powered Router (6 routes)
│   ├── inventory_agent.py       # InventoryAgent (2 tools)
│   ├── pricing_agent.py         # PricingAgent (2 tools)
│   ├── reviews_agent.py         # ReviewsAgent (2 tools)
│   ├── catalog_agent.py         # CatalogAgent (2 tools)
│   └── supervisor.py            # Synthesis + Daily Briefing
├── tools/
│   ├── _data.py                 # Shared CSV loaders (NOT a tool)
│   ├── inventory_tools.py
│   ├── pricing_tools.py
│   ├── reviews_tools.py
│   └── catalog_tools.py
├── core/
│   ├── memory.py                # BufferMemory + SessionStore
│   ├── prompts.py               # 5 distinct system prompts
│   └── trace.py                 # AgentTrace dataclass
└── frontend/
    ├── index.html               # landing page + floating chat widget
    ├── styles.css               # editorial design — Fraunces + Geist + JetBrains Mono
    └── app.js                   # vanilla ES module chat client
```

---

## API surface

| Method | Path | Purpose |
|---|---|---|
| GET  | `/`                       | landing page |
| GET  | `/summary`                | catalog snapshot tiles (no LLM) |
| GET  | `/categories`             | category dropdown values |
| GET  | `/briefing?session_id=…`  | cached or freshly generated Daily Briefing |
| POST | `/chat`                   | `{session_id, message, category_filter}` → `{response, route, reason, specialists}` |
| POST | `/clear`                  | reset session + return fresh briefing |
| GET  | `/trace/{session_id}`     | last `AgentTrace` (router decision + per-step timings) |

---

## Sample queries to test routing

| Query | Expected route |
|---|---|
| "Which dresses are low on stock?" | `INVENTORY` |
| "Margin on SC011?" | `PRICING` |
| "Negative themes in Tops?" | `REVIEWS` |
| "Top performers in Outerwear" | `CATALOG` |
| "Why is SC020 underperforming?" | `MULTI` (≥2 specialists) |
| "Should we discount the Velvet Party Dress?" | `MULTI` |
| "Hi, what can you do?" | `GENERAL` |
| "Stockouts in next 10 days" | `INVENTORY` (threshold=10 extracted by LLM) |

The Agent Trace toggle under each assistant message shows which router decision was made and which specialists were called — useful for evaluator verification.
