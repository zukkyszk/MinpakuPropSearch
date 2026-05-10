from __future__ import annotations
import logging
import re
from .base import BaseScraper, Property
from areas import group_by_pref, address_in_area

logger = logging.getLogger(__name__)

AREA_PATHS = {
    "北海道": "hokkaido/",  "青森県": "aomori/",   "岩手県": "iwate/",
    "宮城県": "miyagi/",    "秋田県": "akita/",    "山形県": "yamagata/",
    "福島県": "fukushima/", "茨城県": "ibaraki/",  "栃木県": "tochigi/",
    "群馬県": "gunma/",     "埼玉県": "saitama/",  "千葉県": "chiba/",
    "東京都": "tokyo/",     "神奈川県": "kanagawa/",
    "新潟県": "niigata/",   "富山県": "toyama/",   "石川県": "ishikawa/",
    "福井県": "fukui/",     "山梨県": "yamanashi/","長野県": "nagano/",
    "岐阜県": "gifu/",      "静岡県": "shizuoka/", "愛知県": "aichi/",
    "三重県": "mie/",       "滋賀県": "shiga/",    "京都府": "kyoto/",
    "大阪府": "osaka/",     "兵庫県": "hyogo/",    "奈良県": "nara/",
    "和歌山県": "wakayama/","広島県": "hiroshima/","福岡県": "fukuoka/",
    "沖縄県": "okinawa/",
}

BASE_URL = "https://www.homes.co.jp"


class HomesScraper(BaseScraper):
    SOURCE = "homes"

    def search(self) -> list[Property]:
        areas = self.config.get("areas", ["東京都"])
        results: list[Property] = []
        for pref, filter_keys in group_by_pref(areas).items():
            path = AREA_PATHS.get(pref)
            if not path:
                logger.warning("HOME'S: エリアパス不明 '%s'、スキップします", pref)
                continue
            props = self._search_area(path, pref)
            if None not in filter_keys:
                props = [p for p in props if address_in_area(p.address, filter_keys)]
            results.extend(props)
        return results

    def _search_area(self, area_path: str, area_name: str) -> list[Property]:
        endpoints = [
            f"/tochi/apartment/{area_path}",
            f"/tochi/mansion/{area_path}",
        ]
        properties: list[Property] = []

        for endpoint in endpoints:
            url = BASE_URL + endpoint
            for page in range(1, 4):
                params = f"?pn={page}" if page > 1 else ""
                soup = self.fetch(url + params)
                if soup is None:
                    break

                items = soup.select(
                    "div[class*='mod-mergeBuilding'], "
                    "li[class*='property'], "
                    "div[class*='prg-cassetteItem'], "
                    "article"
                )
                if not items:
                    logger.debug("HOME'S %s page%d: 物件が見つかりません", area_name, page)
                    break

                for item in items:
                    prop = self._parse_item(item, area_name)
                    if prop:
                        properties.append(prop)

                has_next = soup.select_one(
                    "a[class*='next']:not([class*='disabled']), "
                    "[class*='pagination'] a:last-child"
                )
                if not has_next:
                    break

        logger.info("HOME'S %s: %d件取得", area_name, len(properties))
        return properties

    def _parse_item(self, item, area_name: str) -> Property | None:
        try:
            link_tag = item.select_one("a[href*='/tochi/'], a[href*='/mansion/'], a[href*='/apartment/']")
            if not link_tag:
                link_tag = item.select_one("a[href]")
            if not link_tag:
                return None

            href = link_tag.get("href", "")
            if not href.startswith("http"):
                href = BASE_URL + href

            raw_id = re.search(r"b-(\d+)", href) or re.search(r"/(\d+)/?", href)
            if not raw_id:
                return None
            prop_id = Property.unique_id(self.SOURCE, raw_id.group(1))

            title_tag = item.select_one("h2, h3, [class*='title'], [class*='buildingName']")
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

            price_tag = item.select_one("[class*='price'], [class*='Price']")
            price = self.parse_price(price_tag.get_text()) if price_tag else None

            yield_tag = item.select_one("[class*='yield'], [class*='Yield'], [class*='rimawari']")
            yield_rate = self.parse_yield(yield_tag.get_text()) if yield_tag else None

            addr_tag = item.select_one("[class*='address'], [class*='Address'], [class*='location']")
            address = addr_tag.get_text(strip=True) if addr_tag else ""

            text = item.get_text()
            building_age = self.parse_age(text)

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
            )
        except Exception as e:
            logger.debug("HOME'S parse error: %s", e)
            return None
