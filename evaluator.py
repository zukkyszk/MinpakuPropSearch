from __future__ import annotations
from scrapers.base import Property


def score_property(prop: Property, config: dict) -> int:
    """民泊物件としての適性スコアを算出（0〜100点）"""
    score = 0
    eval_cfg = config.get("evaluation", {})
    search_cfg = config.get("search", {})
    preferred_areas: list[str] = eval_cfg.get("preferred_areas", [])

    # --- 利回り（最大40点）---
    if prop.yield_rate is not None:
        if prop.yield_rate >= 12:
            score += 40
        elif prop.yield_rate >= 10:
            score += 30
        elif prop.yield_rate >= 8:
            score += 20
        elif prop.yield_rate >= search_cfg.get("min_yield", 7):
            score += 10

    # --- 価格（最大20点）---
    if prop.price is not None:
        max_p = search_cfg.get("max_price", 50_000_000)
        min_p = search_cfg.get("min_price", 3_000_000)
        mid_p = (max_p + min_p) / 2
        if min_p <= prop.price <= mid_p:
            score += 20   # 予算の前半は高評価
        elif prop.price <= max_p:
            score += 10

    # --- 築年数（最大20点）---
    if prop.building_age is not None:
        max_age = search_cfg.get("max_building_age", 40)
        if prop.building_age <= 10:
            score += 20
        elif prop.building_age <= 20:
            score += 15
        elif prop.building_age <= 30:
            score += 10
        elif prop.building_age <= max_age:
            score += 5

    # --- 優遇エリア（最大20点）---
    combined = (prop.address + prop.area).replace("　", "")
    for pa in preferred_areas:
        if pa in combined:
            score += 20
            break
    else:
        score += 5  # どのエリアでも最低5点

    return min(score, 100)


def filter_properties(
    properties: list[Property], config: dict
) -> list[Property]:
    """設定条件でフィルタリングし、スコアを付与してソート"""
    search_cfg = config.get("search", {})
    eval_cfg = config.get("evaluation", {})

    min_yield = search_cfg.get("min_yield", 0)
    max_price = search_cfg.get("max_price")
    min_price = search_cfg.get("min_price")
    max_age = search_cfg.get("max_building_age")
    min_score = eval_cfg.get("min_score", 0)

    filtered: list[Property] = []
    for prop in properties:
        # 利回りフィルタ（情報あれば）
        if prop.yield_rate is not None and min_yield and prop.yield_rate < min_yield:
            continue
        # 価格フィルタ（情報あれば）
        if prop.price is not None:
            if max_price and prop.price > max_price:
                continue
            if min_price and prop.price < min_price:
                continue
        # 築年数フィルタ（情報あれば）
        if prop.building_age is not None and max_age and prop.building_age > max_age:
            continue

        prop.score = score_property(prop, config)
        if prop.score >= min_score:
            filtered.append(prop)

    return sorted(filtered, key=lambda p: p.score, reverse=True)
