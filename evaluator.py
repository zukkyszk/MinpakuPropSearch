from __future__ import annotations
import logging
from scrapers.base import Property
from asset_evaluator import AssetEvaluation, evaluate_asset, asset_score

logger = logging.getLogger(__name__)


def score_property(prop: Property, config: dict) -> tuple[int, AssetEvaluation]:
    """
    総合スコアを算出（0〜100点）。
    内訳:
      - 資産性スコア（担保余力 + 居住用利回り）: 50点
      - 民泊利回り:                              25点
      - 価格帯:                                  10点
      - 築年数:                                  10点
      - 優遇エリア:                               5点
    """
    eval_cfg = config.get("evaluation", {})
    search_cfg = config.get("search", {})
    preferred_areas: list[str] = eval_cfg.get("preferred_areas", [])

    # --- 資産性評価（最大50点）---
    ev = evaluate_asset(prop)
    a_score = asset_score(ev)
    score = int(a_score * 0.50)  # 50点満点に換算

    # --- 民泊利回り（最大25点）---
    if prop.yield_rate is not None:
        if prop.yield_rate >= 12:
            score += 25
        elif prop.yield_rate >= 10:
            score += 20
        elif prop.yield_rate >= 8:
            score += 13
        elif prop.yield_rate >= search_cfg.get("min_yield", 7):
            score += 7

    # --- 価格帯（最大10点）---
    if prop.price is not None:
        max_p = search_cfg.get("max_price", 50_000_000)
        min_p = search_cfg.get("min_price", 3_000_000)
        mid_p = (max_p + min_p) / 2
        if min_p <= prop.price <= mid_p:
            score += 10
        elif prop.price <= max_p:
            score += 5

    # --- 築年数（最大10点）---
    if prop.building_age is not None:
        max_age = search_cfg.get("max_building_age", 40)
        if prop.building_age <= 10:
            score += 10
        elif prop.building_age <= 20:
            score += 7
        elif prop.building_age <= 30:
            score += 4
        elif prop.building_age <= max_age:
            score += 2

    # --- 優遇エリア（最大5点）---
    combined = (prop.address + prop.area).replace("　", "")
    for pa in preferred_areas:
        if pa in combined:
            score += 5
            break
    else:
        score += 1

    prop.score = min(score, 100)
    return prop.score, ev


def filter_properties(
    properties: list[Property], config: dict
) -> list[Property]:
    """条件フィルタ → スコア付与 → 上位順でソート"""
    search_cfg = config.get("search", {})
    eval_cfg = config.get("evaluation", {})

    min_yield = search_cfg.get("min_yield", 0)
    max_price = search_cfg.get("max_price")
    min_price = search_cfg.get("min_price")
    max_age = search_cfg.get("max_building_age")
    min_score = eval_cfg.get("min_score", 0)

    result: list[tuple[Property, AssetEvaluation]] = []
    for prop in properties:
        if prop.yield_rate is not None and min_yield and prop.yield_rate < min_yield:
            continue
        if prop.price is not None:
            if max_price and prop.price > max_price:
                continue
            if min_price and prop.price < min_price:
                continue
        if prop.building_age is not None and max_age and prop.building_age > max_age:
            continue

        s, ev = score_property(prop, config)
        if s >= min_score:
            result.append((prop, ev))

    result.sort(key=lambda t: t[0].score, reverse=True)

    # AssetEvaluation を extra に格納して通知側で参照できるようにする
    filtered: list[Property] = []
    for prop, ev in result:
        prop.extra["asset_eval"] = {
            "land_value": ev.land_value,
            "building_value": ev.building_value,
            "collateral_value": ev.collateral_value,
            "collateral_surplus_pct": ev.collateral_surplus_pct,
            "residential_yield": ev.residential_yield,
            "land_price_m2": ev.land_price_m2,
            "data_source": ev.data_source,
        }
        filtered.append(prop)

    return filtered
