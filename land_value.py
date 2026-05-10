"""
土地評価モジュール
国土交通省「不動産取引価格情報」APIと公示地価から土地単価を推計する。
API仕様: https://www.land.mlit.go.jp/webland/api.html
"""
from __future__ import annotations
import logging
import time
from datetime import date
from functools import lru_cache
from typing import Optional
import requests

logger = logging.getLogger(__name__)

MLIT_API = "https://www.land.mlit.go.jp/webland/api/TradeListSearch"

# 市区町村コード（主要地域）
CITY_CODES: dict[str, str] = {
    # 東京都
    "千代田区": "13101", "中央区": "13102", "港区": "13103",
    "新宿区": "13104", "文京区": "13105", "台東区": "13106",
    "墨田区": "13107", "江東区": "13108", "品川区": "13109",
    "目黒区": "13110", "大田区": "13111", "世田谷区": "13112",
    "渋谷区": "13113", "中野区": "13114", "杉並区": "13115",
    "豊島区": "13116", "北区": "13117", "荒川区": "13118",
    "板橋区": "13119", "練馬区": "13120", "足立区": "13121",
    "葛飾区": "13122", "江戸川区": "13123",
    # 大阪府主要区
    "大阪市北区": "27127", "大阪市中央区": "27128",
    "大阪市浪速区": "27132", "大阪市西区": "27133",
    "大阪市天王寺区": "27134", "大阪市難波": "27128",
    # 京都府
    "京都市中京区": "26106", "京都市東山区": "26107",
    "京都市下京区": "26108", "京都市右京区": "26111",
    # 都道府県コード（フォールバック用）
    "東京都": "13100", "大阪府": "27100", "京都府": "26100",
    "神奈川県": "14100", "愛知県": "23100", "福岡県": "40100",
}

# 路線価ベースの土地単価概算（円/m²）
# 実際の路線価に基づく主要エリアの目安値
AREA_LAND_PRICE_M2: dict[str, int] = {
    # 東京都心
    "千代田区": 3_500_000, "中央区": 2_200_000, "港区": 2_800_000,
    "新宿区": 1_800_000, "渋谷区": 2_500_000, "台東区": 1_200_000,
    "文京区": 1_100_000, "墨田区": 700_000,  "江東区": 650_000,
    "品川区": 950_000,  "目黒区": 1_100_000, "大田区": 600_000,
    "世田谷区": 650_000, "中野区": 700_000,  "杉並区": 600_000,
    "豊島区": 900_000,  "北区": 550_000,    "荒川区": 550_000,
    "板橋区": 500_000,  "練馬区": 480_000,  "足立区": 380_000,
    "葛飾区": 380_000,  "江戸川区": 380_000,
    # 大阪
    "大阪市北区": 1_800_000, "大阪市中央区": 1_600_000,
    "大阪市浪速区": 900_000,  "大阪市西区": 1_100_000,
    "大阪市天王寺区": 700_000, "大阪市": 400_000,
    # 京都
    "京都市中京区": 700_000,  "京都市東山区": 600_000,
    "京都市下京区": 600_000,  "京都市": 350_000,
    # デフォルト（都道府県）
    "東京都": 450_000, "大阪府": 250_000, "京都府": 220_000,
    "神奈川県": 280_000, "愛知県": 180_000, "福岡県": 150_000,
}


def _current_quarter() -> tuple[str, str]:
    """現在の四半期と1年前の四半期を返す (例: '20244', '20234')"""
    d = date.today()
    q = (d.month - 1) // 3 + 1
    to_str = f"{d.year}{q}"
    prev_year = d.year - 1
    from_str = f"{prev_year}{q}"
    return from_str, to_str


@lru_cache(maxsize=64)
def _fetch_mlit_transactions(city_code: str, transaction_type: str = "1") -> list[dict]:
    """国土交通省APIから不動産取引価格を取得（宅地）"""
    from_q, to_q = _current_quarter()
    params = {
        "from": from_q,
        "to": to_q,
        "city": city_code,
        "type": transaction_type,  # 1=宅地(土地), 2=土地+建物
    }
    try:
        time.sleep(1)
        resp = requests.get(MLIT_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        logger.debug("国土交通省API エラー (%s): %s", city_code, e)
        return []


def get_land_price_m2(address: str, area: str) -> tuple[Optional[int], str]:
    """
    住所・エリアから土地単価（円/m²）を推計する。
    戻り値: (単価, データソース)
    """
    # 1. 国土交通省APIで実取引データから算出
    city_code = _resolve_city_code(address, area)
    if city_code:
        transactions = _fetch_mlit_transactions(city_code, "1")
        if transactions:
            prices = []
            for t in transactions:
                unit_price = t.get("UnitPrice") or t.get("PricePerUnit")
                try:
                    if unit_price:
                        prices.append(int(str(unit_price).replace(",", "")))
                except (ValueError, TypeError):
                    pass
            if prices:
                # 中央値を使用（外れ値の影響を排除）
                prices.sort()
                median = prices[len(prices) // 2]
                logger.debug("国土交通省API: %s %d件 中央値 %d円/m²", area, len(prices), median)
                return median, "mlit_api"

    # 2. 路線価概算テーブルにフォールバック
    combined = address + " " + area
    for key, price in AREA_LAND_PRICE_M2.items():
        if key in combined:
            logger.debug("路線価概算テーブル: %s → %d円/m²", key, price)
            return price, "estimate"

    return None, "unknown"


def _resolve_city_code(address: str, area: str) -> Optional[str]:
    """住所文字列から市区町村コードを引く"""
    combined = (address + " " + area).replace("　", " ")
    for name, code in CITY_CODES.items():
        if name in combined:
            return code
    return None
