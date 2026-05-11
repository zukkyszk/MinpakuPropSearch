from __future__ import annotations
import logging
import re
from .base import BaseScraper, Property
from areas import group_by_pref, address_in_area

logger = logging.getLogger(__name__)

# toushi-athome.jp エリアコード（地域コード_JIS都道府県コード）
# 12=関東, 13=中部・甲信越, 14=近畿, 16=中国, 17=九州・沖縄
AREA_CODES = {
    "北海道": "1_11_01",
    "青森県": "1_10_02", "岩手県": "1_10_03", "宮城県": "1_10_04",
    "秋田県": "1_10_05", "山形県": "1_10_06", "福島県": "1_10_07",
    "茨城県": "1_12_08", "栃木県": "1_12_09", "群馬県": "1_12_10",
    "埼玉県": "1_12_11", "千葉県": "1_12_12", "東京都": "1_12_13",
    "神奈川県": "1_12_14",
    "新潟県": "1_13_15", "富山県": "1_13_16", "石川県": "1_13_17",
    "福井県": "1_13_18", "山梨県": "1_13_19", "長野県": "1_13_20",
    "岐阜県": "1_13_21", "静岡県": "1_13_22", "愛知県": "1_13_23",
    "三重県": "1_14_24",
    "滋賀県": "1_14_25", "京都府": "1_14_26", "大阪府": "1_14_27",
    "兵庫県": "1_14_28", "奈良県": "1_14_29", "和歌山県": "1_14_30",
    "広島県": "1_16_34",
    "福岡県": "1_17_40", "沖縄県": "1_17_47",
}

BASE_URL = "https://toushi-athome.jp"

# 検索する物件タイプ（一棟マンション/アパート、戸建て）
SEARCH_TYPES = ["ei_42", "ei_43"]


class AtHomeScraper(BaseScraper):
    SOURCE = "athome"

    def search(self) -> list[Property]:
        areas = self.config.get("areas", ["東京都"])
        results: list[Property] = []
        for pref, filter_keys in group_by_pref(areas).items():
            code = AREA_CODES.get(pref)
            if not code:
                logger.warning("AtHome: エリアコード不明 '%s'、スキップします", pref)
                continue
            props = self._search_area(code, pref)
            if None not in filter_keys:
                props = [p for p in props if address_in_area(p.address, filter_keys)]
            results.extend(props)
        return results

    def _search_area(self, area_code: str, area_name: str) -> list[Property]:
        properties: list[Property] = []

        for prop_type in SEARCH_TYPES:
            for page in range(1, 4):
                if page == 1:
                    url = f"{BASE_URL}/{prop_type}/{area_code}/"
                else:
                    url = f"{BASE_URL}/{prop_type}/{area_code}/?page={page}"
                soup = self.fetch(url)
                if soup is None:
                    break

                items = soup.select(
                    "li[class*='property'], "
                    "article[class*='property'], "
                    "div[class*='property-item'], "
                    "div[class*='bukken'], "
                    "li[class*='bukken']"
                )
                if not items:
                    items = soup.select("[class*='cassette'], [class*='list-item']")

                if not items:
                    logger.debug("AtHome %s %s page%d: 物件が見つかりません", area_name, prop_type, page)
                    break

                for item in items:
                    prop = self._parse_item(item, area_name)
                    if prop:
                        properties.append(prop)

                if not soup.select("[class*='next']:not([class*='disabled']), a[rel='next']"):
                    break

        logger.info("AtHome %s: %d件取得", area_name, len(properties))
        return properties

    def _parse_item(self, item, area_name: str) -> Property | None:
        try:
            link_tag = item.select_one("a[href*='toushi-athome.jp'], a[href*='/ei_']")
            if not link_tag:
                link_tag = item.select_one("a[href]")
            if not link_tag:
                return None
            href = link_tag.get("href", "")
            if not href.startswith("http"):
                href = BASE_URL + href

            raw_id = re.search(r"lst_(\d+)", href) or re.search(r"-(\d+)[_-]", href) or re.search(r"/(\d+)/?$", href)
            if not raw_id:
                return None
            prop_id = Property.unique_id(self.SOURCE, raw_id.group(1))

            title_tag = item.select_one("h2, h3, [class*='title'], [class*='name']")
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

            price_tag = item.select_one("[class*='price'], [class*='kakaku']")
            price = self.parse_price(price_tag.get_text()) if price_tag else None

            yield_tag = item.select_one("[class*='yield'], [class*='rimawari']")
            yield_rate = self.parse_yield(yield_tag.get_text()) if yield_tag else None

            addr_tag = item.select_one("[class*='address'], [class*='location']")
            address = addr_tag.get_text(strip=True) if addr_tag else ""

            text = item.get_text()
            building_age = self.parse_age(text)
            published_date = self._extract_date_from_item(item)

            return Property(
                id=prop_id,
                source=self.SOURCE,
                title=title,
                url=href,
                price=price,
                yield_rate=yield_rate,
                area=area_name,
                address=address,
                building_age=building_age,
                published_date=published_date,
            )
        except Exception as e:
            logger.debug("AtHome parse error: %s", e)
            return None
