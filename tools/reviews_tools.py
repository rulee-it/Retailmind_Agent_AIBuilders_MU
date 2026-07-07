"""ReviewsAgent tools.

Strict isolation: imported ONLY by agents/reviews_agent.py.

Each tool makes a small LLM call for thematic summarisation; results are
cached to avoid re-summarising on Daily-Briefing replay.
"""
from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from ._data import get_product, normalize_category, reviews_df


_INSIGHT_CACHE: dict[str, dict] = {}
_THEME_CACHE: dict[str, dict] = {}


def _summarizer_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        max_tokens=400,
    )


def _safe_json(content: str, fallback: dict) -> dict:
    try:
        start = content.index("{")
        end = content.rindex("}") + 1
        return json.loads(content[start:end])
    except Exception:
        return fallback


@tool
def get_review_insights(product_id: str) -> dict:
    """Return customer-review insights for a single SKU.

    Use for "what are people saying about SC011?", "sentiment on the
    velvet dress", "show me complaints for SC025". Pass product_id.

    Returns avg_rating, total_reviews, sentiment_summary (2 sentences),
    positive_themes (list) and negative_themes (list).
    """
    pid = str(product_id).strip().upper()
    if pid in _INSIGHT_CACHE:
        return _INSIGHT_CACHE[pid]
    p = get_product(pid)
    if p is None:
        return {"error": f"Unknown product_id '{pid}'."}
    rdf = reviews_df()
    sub = rdf[rdf["product_id"] == pid]
    if sub.empty:
        result: dict[str, Any] = {
            "product_id": pid,
            "product_name": p["product_name"],
            "avg_rating": None,
            "total_reviews": 0,
            "sentiment_summary": "No customer reviews available for this product yet.",
            "positive_themes": [],
            "negative_themes": [],
        }
        _INSIGHT_CACHE[pid] = result
        return result

    text = "\n".join(f"- ({int(r)}/5) {t}" for r, t in zip(sub["rating"], sub["review_text"]))[:4000]
    llm = _summarizer_llm()
    sys = SystemMessage(
        content=(
            "You summarise customer reviews into structured JSON. "
            "Return EXACTLY this JSON shape and nothing else: "
            '{"sentiment_summary": "<2 sentences>", '
            '"positive_themes": ["theme1", "theme2"], '
            '"negative_themes": ["theme1", "theme2"]} '
            "Themes are short noun phrases (e.g., 'Fabric quality', 'Sizing inconsistency'). "
            "Cap each list at 4 items."
        )
    )
    usr = HumanMessage(content=f"Product: {p['product_name']}\nReviews:\n{text}")
    raw = llm.invoke([sys, usr]).content
    parsed = _safe_json(
        raw if isinstance(raw, str) else str(raw),
        {"sentiment_summary": "Mixed reviews.", "positive_themes": [], "negative_themes": []},
    )
    result = {
        "product_id": pid,
        "product_name": p["product_name"],
        "avg_rating": round(float(sub["rating"].mean()), 2),
        "total_reviews": int(len(sub)),
        "sentiment_summary": parsed.get("sentiment_summary", ""),
        "positive_themes": parsed.get("positive_themes", []),
        "negative_themes": parsed.get("negative_themes", []),
    }
    _INSIGHT_CACHE[pid] = result
    return result


@tool
def get_negative_review_themes(category: str) -> dict:
    """Cluster low-rated (≤2★) reviews in a category into top 3 themes.

    Use for "negative themes in Tops?", "what are people complaining
    about in Outerwear?". Pass a category name (Tops/Dresses/Bottoms/
    Outerwear/Accessories) or "All" to scan everything.

    Returns category, total_negative_reviews, top_3_themes (list of
    theme strings) and affected_products (list of product_ids).
    """
    canon = normalize_category(category) or "All"
    cache_key = canon
    if cache_key in _THEME_CACHE:
        return _THEME_CACHE[cache_key]

    rdf = reviews_df()
    if canon != "All":
        from ._data import products_df

        prods = products_df()
        ids_in_cat = set(prods[prods["category"] == canon]["product_id"])
        sub = rdf[rdf["product_id"].isin(ids_in_cat)]
    else:
        sub = rdf
    sub = sub[sub["rating"] <= 2]
    if sub.empty:
        result = {
            "category": canon,
            "total_negative_reviews": 0,
            "top_3_themes": [],
            "affected_products": [],
        }
        _THEME_CACHE[cache_key] = result
        return result

    text = "\n".join(f"- {pid}: ({int(r)}/5) {t}" for pid, r, t in zip(sub["product_id"], sub["rating"], sub["review_text"]))[:4000]
    llm = _summarizer_llm()
    sys = SystemMessage(
        content=(
            "You cluster negative customer reviews into themes. "
            "Return EXACTLY this JSON: "
            '{"top_3_themes": ["theme1", "theme2", "theme3"]} '
            "Themes are short noun phrases."
        )
    )
    usr = HumanMessage(content=f"Category: {canon}\nNegative reviews:\n{text}")
    raw = llm.invoke([sys, usr]).content
    parsed = _safe_json(raw if isinstance(raw, str) else str(raw), {"top_3_themes": []})
    result = {
        "category": canon,
        "total_negative_reviews": int(len(sub)),
        "top_3_themes": parsed.get("top_3_themes", [])[:3],
        "affected_products": sorted(set(sub["product_id"].tolist())),
    }
    _THEME_CACHE[cache_key] = result
    return result


REVIEWS_TOOLS = [get_review_insights, get_negative_review_themes]
