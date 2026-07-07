"""Shared CSV loaders. NOT a tool — internal helpers only."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRODUCTS_CSV = DATA_DIR / "retailmind_products.csv"
REVIEWS_CSV = DATA_DIR / "retailmind_reviews.csv"

# Canonical category names
CATEGORIES = ["Tops", "Dresses", "Bottoms", "Outerwear", "Accessories"]


@lru_cache(maxsize=1)
def products_df() -> pd.DataFrame:
    df = pd.read_csv(PRODUCTS_CSV)
    df["product_id"] = df["product_id"].astype(str).str.strip().str.upper()
    df["category"] = df["category"].astype(str).str.strip()
    return df


@lru_cache(maxsize=1)
def reviews_df() -> pd.DataFrame:
    df = pd.read_csv(REVIEWS_CSV)
    df["product_id"] = df["product_id"].astype(str).str.strip().str.upper()
    return df


def normalize_category(c: str | None) -> str | None:
    """Map user-typed category strings to canonical names. None / 'all' / '' → None."""
    if c is None:
        return None
    s = c.strip().lower()
    if s in {"", "all", "all categories", "any"}:
        return None
    aliases = {
        "top": "Tops", "tops": "Tops", "shirt": "Tops", "shirts": "Tops",
        "dress": "Dresses", "dresses": "Dresses",
        "bottom": "Bottoms", "bottoms": "Bottoms", "pants": "Bottoms", "jeans": "Bottoms",
        "outerwear": "Outerwear", "jacket": "Outerwear", "jackets": "Outerwear", "coat": "Outerwear", "coats": "Outerwear",
        "accessory": "Accessories", "accessories": "Accessories",
    }
    return aliases.get(s, c.strip().title() if c.strip().title() in CATEGORIES else None)


def get_product(pid: str) -> dict | None:
    pid = str(pid).strip().upper()
    df = products_df()
    row = df[df["product_id"] == pid]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def category_products(category: str) -> pd.DataFrame:
    canon = normalize_category(category)
    df = products_df()
    if canon is None:
        return df
    return df[df["category"] == canon]
