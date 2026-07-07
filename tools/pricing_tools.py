"""PricingAgent tools.

Strict isolation: imported ONLY by agents/pricing_agent.py.
"""
from __future__ import annotations

from langchain_core.tools import tool

from ._data import category_products, get_product


def _gross_margin_pct(price: float, cost: float) -> float:
    if price <= 0:
        return 0.0
    return (price - cost) / price * 100.0


@tool
def get_pricing_analysis(product_id: str) -> dict:
    """Return margin and price-positioning analysis for a single SKU.

    Use for questions about gross margin %, profitability, or whether a
    product is premium/mid-range/budget. Pass product_id like "SC011".

    Returns gross_margin_percent, price_positioning, margin_flag
    (True if margin < 20%) and a suggested_action.
    """
    p = get_product(product_id)
    if p is None:
        return {"error": f"Unknown product_id '{product_id}'."}
    cohort = category_products(p["category"])
    cat_avg = float(cohort["price"].mean())
    margin = _gross_margin_pct(float(p["price"]), float(p["cost"]))
    if p["price"] > cat_avg * 1.25:
        positioning = "Premium"
    elif p["price"] < cat_avg * 0.75:
        positioning = "Budget"
    else:
        positioning = "Mid-Range"
    flag = margin < 20.0
    action = (
        f"Margin only {margin:.1f}% — review COGS or reposition pricing."
        if flag
        else f"Healthy {margin:.1f}% margin — maintain current pricing."
    )
    return {
        "product_id": p["product_id"],
        "product_name": p["product_name"],
        "category": p["category"],
        "price": float(p["price"]),
        "cost": float(p["cost"]),
        "gross_margin_percent": round(margin, 2),
        "category_avg_price": round(cat_avg, 2),
        "price_positioning": positioning,
        "margin_flag": flag,
        "suggested_action": action,
    }


@tool
def compare_category_pricing(product_id: str) -> dict:
    """Compare a product's price against its category cohort.

    Use for "is X overpriced?", "how does X compare on price to the
    category?", "is X underpriced vs peers?". Pass product_id.

    Returns product_price, category_avg/min/max, percentile_rank (0–100)
    and verdict: Underpriced (<25th pct), On Trend (25–75), Overpriced (>75th).
    """
    p = get_product(product_id)
    if p is None:
        return {"error": f"Unknown product_id '{product_id}'."}
    cohort = category_products(p["category"])
    prices = cohort["price"].astype(float).tolist()
    pct_rank = (sum(1 for x in prices if x < float(p["price"])) / len(prices)) * 100.0
    if pct_rank < 25:
        verdict = "Underpriced"
    elif pct_rank > 75:
        verdict = "Overpriced"
    else:
        verdict = "On Trend"
    return {
        "product_id": p["product_id"],
        "product_name": p["product_name"],
        "category": p["category"],
        "product_price": float(p["price"]),
        "category_avg_price": round(float(cohort["price"].mean()), 2),
        "category_min_price": float(cohort["price"].min()),
        "category_max_price": float(cohort["price"].max()),
        "percentile_rank": round(pct_rank, 1),
        "verdict": verdict,
    }


PRICING_TOOLS = [get_pricing_analysis, compare_category_pricing]
