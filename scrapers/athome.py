from __future__ import annotations
import logging
import re
from .base import BaseScraper, Property

logger = logging.getLogger(__name__)

# AtHome 収益物件検索（売りアパ・マンション）エリアスラッグ
AREA_SLUGS = {
    "東京都": "tokyo",
    "大阪府": "osaka",
    "京都府": "kyoto",
    "神奈川県": "kanagawa",
    "愛知県": "aichi",
    "福岡県": "fukuoka",
    "北海道": "hokkaido",
    "沖縄県": "okinawa",
}

BASE_URL = "https://www.athome.co.jp"


class AtHomeScraper(BaseScraper):
    SOURCE = "athome"

    def search(self) -> list[Property]:
        areas = self.config.get("areas", ["東京都"])
        results: list[Property] = []
        for area in areas:
            slug = AREA_SLUGS.get(area)
            if not slug:
                logger.warning("AtHome: エリアスラッグ不明 '%s'、スキップします", area)
                continue
            props = self._search_area(slug, area)
            results.extend(props)
        return results

    def _search_area(self, slug: str, area_name: str) -> list[Property]:
        # 収益物件（投資用マンション・アパート・一棟ビル）
        search_types = [
            f"/tochi/apartment/{slug}/",       # 売りアパート
            f"/tochi/mansion/{slug}/",          # 売りマンション一棟
        ]
        properties: list[Property] = []

        for path in search_types:
            url = BASE_URL + path
            for page in range(1, 4):
                page_url = url + (f"?page={page}" if page > 1 else "")
                soup = self.fetch(page_url)
                if soup is None:
                    break

                items = soup.select(
                    "li[class*='property'], "
                    "article[class*='property'], "
                    "div[class*='estate-item'], "
                    "div[class*='property-item']"
                )
                if not items:
                    logger.debug("AtHome %s page%d: 物件が見つかりません", area_name, page)
                    break

                for item in items:
                    prop = self._parse_item(item, area_name)
                    if prop:
                        properties.append(prop)

                if not soup.select("[class*='next']:not([class*='disabled'])"):
                    break

        logger.info("AtHome %s: %d件取得", area_name, len(properties))
        return properties

    def _parse_item(self, item, area_name: str) -> Property | None:
        try:
            link_tag = item.select_one("a[href]")
            if not link_tag:
                return None
            href = link_tag.get("href", "")
            if not href.startswith("http"):
                href = BASE_URL + href

            raw_id = re.search(r"_(\d+)/?", href) or re.search(r"/(\d+)/?$", href)
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
            logger.debug("AtHome parse error: %s", e)
            return None
