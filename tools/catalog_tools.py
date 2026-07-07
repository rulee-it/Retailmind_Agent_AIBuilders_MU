"""CatalogAgent tools.

Strict isolation: imported ONLY by agents/catalog_agent.py.
"""
from __future__ import annotations

from langchain_core.tools import tool

from ._data import category_products, normalize_category, products_df


@tool
def search_products(query: str, category: str | None = None) -> list[dict]:
    """Search the StyleCraft catalog by name. Returns top 5 matches.

    Pass `query` as a keyword/phrase (e.g., "linen", "trench", "evening dress").
    Optionally pass `category` to scope the search (Tops/Dresses/Bottoms/
    Outerwear/Accessories). If `query` is empty, returns the top 5 most-
    reviewed products in the category (or overall if no category).
    """
    canon = normalize_category(category) if category else None
    df = products_df() if canon is None else category_products(canon)
    q = (query or "").strip().lower()
    if not q:
        ranked = df.sort_values("review_count", ascending=False).head(5)
    else:
        mask = df["product_name"].str.lower().str.contains(q, na=False)
        ranked = df[mask].head(5)
        if ranked.empty:
            ranked = df.sort_values("review_count", ascending=False).head(5)
    out = []
    for _, p in ranked.iterrows():
        out.append(
            {
                "product_id": p["product_id"],
                "product_name": p["product_name"],
                "category": p["category"],
                "price": float(p["price"]),
                "stock_quantity": int(p["stock_quantity"]),
                "avg_rating": float(p["avg_rating"]),
            }
        )
    return out


@tool
def get_category_performance(category: str) -> dict:
    """Aggregate performance snapshot for a category (or "All" for catalog-wide).

    Use for "category overview for Bottoms", "how is Outerwear doing?",
    "snapshot of all categories". Pass "All" to aggregate everything.

    Returns total_skus, avg_rating, avg_margin_percent, total_stock_units,
    low_stock_count (7–14 days), critical_stock_count (<7 days),
    top_3_revenue_products (by 30-day revenue projection).
    """
    canon = normalize_category(category)
    df = products_df() if canon is None else category_products(canon)
    label = canon or "All"
    if df.empty:
        return {"category": label, "total_skus": 0, "message": "No products found."}

    margins = ((df["price"] - df["cost"]) / df["price"] * 100.0).astype(float)
    safe_daily = df["avg_daily_sales"].replace(0, float("nan"))
    d2s = (df["stock_quantity"] / safe_daily).fillna(float("inf"))

    revenue_30d = (df["price"] * df["avg_daily_sales"] * 30).astype(float)
    top3_idx = revenue_30d.sort_values(ascending=False).head(3).index
    top3 = [
        {
            "product_id": df.loc[i, "product_id"],
            "product_name": df.loc[i, "product_name"],
            "projected_30d_revenue": round(float(revenue_30d.loc[i]), 2),
        }
        for i in top3_idx
    ]
    return {
        "category": label,
        "total_skus": int(len(df)),
        "avg_rating": round(float(df["avg_rating"].mean()), 2),
        "avg_margin_percent": round(float(margins.mean()), 2),
        "total_stock_units": int(df["stock_quantity"].sum()),
        "low_stock_count": int(((d2s >= 7) & (d2s <= 14)).sum()),
        "critical_stock_count": int((d2s < 7).sum()),
        "top_3_revenue_products": top3,
    }


CATALOG_TOOLS = [search_products, get_category_performance]
