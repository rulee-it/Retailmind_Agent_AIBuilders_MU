"""InventoryAgent tools.

Strict isolation: this file is imported ONLY by agents/inventory_agent.py.
"""
from __future__ import annotations

from langchain_core.tools import tool

from ._data import get_product, products_df


def _days_to_stockout(stock: float, daily: float) -> float | None:
    if daily is None or daily <= 0:
        return None
    return float(stock) / float(daily)


def _status_flag(d2s: float | None) -> str:
    if d2s is None:
        return "Stagnant"
    if d2s < 7:
        return "Critical"
    if d2s <= 14:
        return "Low"
    return "Healthy"


@tool
def get_inventory_health(product_id: str) -> dict:
    """Return single-product inventory health.

    Use for questions about a specific SKU's stock status, days to stockout,
    or whether a product is at risk. Pass the product_id like "SC011".

    Returns a dict with stock_quantity, avg_daily_sales, days_to_stockout,
    status_flag (Critical / Low / Healthy / Stagnant) and a one-line message.
    Returns {"error": "..."} for unknown SKUs.
    """
    p = get_product(product_id)
    if p is None:
        return {"error": f"Unknown product_id '{product_id}'. Valid SKUs look like SC001…SC030."}
    d2s = _days_to_stockout(p["stock_quantity"], p["avg_daily_sales"])
    flag = _status_flag(d2s)
    msg = (
        f"{p['product_name']} ({p['product_id']}): "
        f"{int(p['stock_quantity'])} units, "
        + (f"~{d2s:.1f} days to stockout" if d2s is not None else "no recent sales")
        + f" — {flag}."
    )
    return {
        "product_id": p["product_id"],
        "product_name": p["product_name"],
        "category": p["category"],
        "stock_quantity": int(p["stock_quantity"]),
        "avg_daily_sales": float(p["avg_daily_sales"]),
        "days_to_stockout": round(d2s, 2) if d2s is not None else None,
        "status_flag": flag,
        "message": msg,
    }


@tool
def generate_restock_alert(threshold_days: int = 7) -> list[dict]:
    """Return all products that will stock out within `threshold_days` days,
    sorted by urgency (smallest days_to_stockout first).

    Use this for queries like "what needs restocking?", "stockouts in the
    next 10 days", "which products are critical?". Default threshold is 7
    days; pass a larger number when the user mentions a wider window.

    Each item includes product_id, product_name, category, days_to_stockout,
    revenue_at_risk (₹), and a recommended restock_action.
    """
    df = products_df()
    out: list[dict] = []
    for _, p in df.iterrows():
        d2s = _days_to_stockout(p["stock_quantity"], p["avg_daily_sales"])
        if d2s is None or d2s >= threshold_days:
            continue
        revenue_at_risk = float(p["price"]) * (
            float(p["stock_quantity"]) + float(p["avg_daily_sales"]) * threshold_days
        )
        suggested_units = max(int(round(p["avg_daily_sales"] * 30)), int(p["reorder_level"]))
        out.append(
            {
                "product_id": p["product_id"],
                "product_name": p["product_name"],
                "category": p["category"],
                "stock_quantity": int(p["stock_quantity"]),
                "days_to_stockout": round(d2s, 2),
                "revenue_at_risk": round(revenue_at_risk, 2),
                "restock_action": f"Order {suggested_units} units within {max(1, int(d2s))} day(s).",
            }
        )
    out.sort(key=lambda x: x["days_to_stockout"])
    return out


INVENTORY_TOOLS = [get_inventory_health, generate_restock_alert]
