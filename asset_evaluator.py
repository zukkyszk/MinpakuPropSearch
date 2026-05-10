"""
資産性評価モジュール
- 土地評価額（路線価/公示地価ベース）
- 建物評価額（法定耐用年数ベース減価償却）
- 担保評価合計と担保余力
- 居住用賃貸として運用した場合の想定利回り
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from typing import Optional

from scrapers.base import Property
from land_value import get_land_price_m2

logger = logging.getLogger(__name__)

# 構造別の建築単価（円/m²）と法定耐用年数
STRUCTURE_TABLE = {
    "木造":       {"cost_m2": 160_000, "useful_life": 22},
    "軽量鉄骨":   {"cost_m2": 190_000, "useful_life": 27},
    "鉄骨":       {"cost_m2": 230_000, "useful_life": 34},
    "重量鉄骨":   {"cost_m2": 230_000, "useful_life": 34},
    "RC":         {"cost_m2": 290_000, "useful_life": 47},
    "鉄筋コンクリート": {"cost_m2": 290_000, "useful_life": 47},
    "SRC":        {"cost_m2": 310_000, "useful_life": 47},
    "鉄骨鉄筋":   {"cost_m2": 310_000, "useful_life": 47},
}
DEFAULT_STRUCTURE = {"cost_m2": 180_000, "useful_life": 25}

# 銀行の担保掛け目（一般的な水準）
LAND_COLLATERAL_RATE = 0.80     # 土地: 80%
BUILDING_COLLATERAL_RATE = 0.70  # 建物: 70%

# エリア別 居住用想定月額賃料単価（円/m²）
# 普通賃貸として1棟丸ごと貸し出した場合の満室想定
RENT_M2_TABLE: dict[str, int] = {
    # 東京都心
    "千代田区": 4_200, "中央区": 3_800, "港区": 4_000,
    "新宿区": 3_200,  "渋谷区": 3_800, "台東区": 2_800,
    "文京区": 2_900,  "品川区": 2_700, "目黒区": 2_900,
    "世田谷区": 2_500, "豊島区": 2_800, "中野区": 2_400,
    "大田区": 2_200,  "足立区": 1_800, "葛飾区": 1_800,
    # 大阪
    "大阪市北区": 2_800, "大阪市中央区": 2_600, "大阪市浪速区": 1_900,
    "大阪市西区": 2_200, "大阪市天王寺区": 1_800, "大阪市": 1_600,
    # 京都
    "京都市中京区": 2_200, "京都市東山区": 2_000, "京都市下京区": 2_000,
    "京都市": 1_700,
    # デフォルト
    "東京都": 2_000, "大阪府": 1_500, "京都府": 1_400,
}
DEFAULT_RENT_M2 = 1_200
OCCUPANCY_RATE = 0.90  # 居住用想定稼働率 90%


@dataclass
class AssetEvaluation:
    land_value: Optional[int] = None         # 土地評価額（円）
    building_value: Optional[int] = None     # 建物評価額（円）
    collateral_value: Optional[int] = None   # 担保評価合計（円）
    collateral_surplus_pct: Optional[float] = None  # 担保余力 (%)
    residential_yield: Optional[float] = None       # 居住用利回り (%)
    land_price_m2: Optional[int] = None      # 土地単価 (円/m²)
    data_source: str = "unknown"


def _detect_structure(prop: Property) -> dict:
    """物件タイトル・説明から建物構造を推定"""
    text = prop.title + " " + prop.description + " " + prop.extra.get("raw_text", "")
    for key in STRUCTURE_TABLE:
        if key in text:
            return STRUCTURE_TABLE[key]
    return DEFAULT_STRUCTURE


_MAX_AREA_M2 = 10_000   # 1棟物件として現実的な上限（1万m²）
_MAX_LAND_M2 = 50_000   # 土地面積の現実的な上限


def _clamp_area(value: float, max_val: float) -> Optional[float]:
    """スクレイプ値の異常値ガード"""
    if value <= 0 or value > max_val:
        return None
    return value


def _estimate_floor_area(prop: Property) -> Optional[float]:
    """延床面積が未入力の場合、物件情報テキストから推定"""
    if prop.floor_area:
        return _clamp_area(prop.floor_area, _MAX_AREA_M2)
    text = prop.title + " " + prop.description + " " + prop.extra.get("raw_text", "")
    m = re.search(r"延床[面積]?\s*[:：]?\s*(\d+(?:\.\d+)?)\s*m", text)
    if m:
        return _clamp_area(float(m.group(1)), _MAX_AREA_M2)
    # 土地面積があれば土地の60%を延床面積として概算
    if prop.land_area:
        clamped = _clamp_area(prop.land_area, _MAX_LAND_M2)
        return clamped * 0.6 if clamped else None
    return None


def _estimate_rent_m2(address: str, area: str) -> int:
    combined = address + " " + area
    for key, rent in RENT_M2_TABLE.items():
        if key in combined:
            return rent
    return DEFAULT_RENT_M2


def evaluate_asset(prop: Property) -> AssetEvaluation:
    """物件の資産性を評価して AssetEvaluation を返す"""
    result = AssetEvaluation()

    # --- 土地評価 ---
    land_price_m2, source = get_land_price_m2(prop.address, prop.area)
    result.data_source = source

    land_area = prop.land_area
    if land_price_m2 and land_area:
        result.land_price_m2 = land_price_m2
        result.land_value = int(land_area * land_price_m2 * LAND_COLLATERAL_RATE)

    # --- 建物評価 ---
    floor_area = _estimate_floor_area(prop)
    structure = _detect_structure(prop)
    building_age = prop.building_age or 15  # 不明時は15年と仮定

    if floor_area:
        useful_life = structure["useful_life"]
        cost_m2 = structure["cost_m2"]
        # 残存価値率（最低10%）
        survival_rate = max(0.10, 1.0 - building_age / useful_life)
        building_replacement_cost = floor_area * cost_m2
        result.building_value = int(
            building_replacement_cost * survival_rate * BUILDING_COLLATERAL_RATE
        )

    # --- 担保評価合計 ---
    if result.land_value is not None or result.building_value is not None:
        result.collateral_value = (result.land_value or 0) + (result.building_value or 0)

    # --- 担保余力 ---
    if result.collateral_value is not None and prop.price:
        surplus = result.collateral_value - prop.price
        result.collateral_surplus_pct = round(surplus / prop.price * 100, 1)

    # --- 居住用利回り ---
    if floor_area and prop.price:
        rent_m2 = _estimate_rent_m2(prop.address, prop.area)
        annual_rent = floor_area * rent_m2 * 12 * OCCUPANCY_RATE
        result.residential_yield = round(annual_rent / prop.price * 100, 2)

    return result


def asset_score(ev: AssetEvaluation) -> int:
    """資産性評価スコア（0〜100点）"""
    score = 0

    # 担保余力（最大50点）
    if ev.collateral_surplus_pct is not None:
        if ev.collateral_surplus_pct >= 30:
            score += 50   # 担保が物件価格より30%以上上回る
        elif ev.collateral_surplus_pct >= 10:
            score += 35
        elif ev.collateral_surplus_pct >= 0:
            score += 20   # 担保割れなし
        elif ev.collateral_surplus_pct >= -10:
            score += 10   # 軽微な担保割れ
        # -10%以下は0点

    # 居住用利回り（最大50点）
    if ev.residential_yield is not None:
        if ev.residential_yield >= 8:
            score += 50
        elif ev.residential_yield >= 6:
            score += 35
        elif ev.residential_yield >= 4:
            score += 20
        elif ev.residential_yield >= 2:
            score += 10

    return min(score, 100)
