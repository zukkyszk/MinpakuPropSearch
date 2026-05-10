from __future__ import annotations
import logging
import re
from urllib.parse import urlencode
from .base import BaseScraper, Property

logger = logging.getLogger(__name__)

# 楽待エリアコード（主要府県）
AREA_CODES = {
    "東京都": "13",
    "大阪府": "27",
    "京都府": "26",
    "神奈川県": "14",
    "愛知県": "23",
    "福岡県": "40",
    "北海道": "01",
    "沖縄県": "47",
}

BASE_URL = "https://www.rakumachi.jp/syuuekibukkens/"


class RakumachiScraper(BaseScraper):
    SOURCE = "rakumachi"

    def search(self) -> list[Property]:
        areas = self.config.get("areas", ["東京都"])
        min_yield = self.config.get("min_yield", 0)
        min_price = self.config.get("min_price")
        max_price = self.config.get("max_price")

        results: list[Property] = []
        for area in areas:
            code = AREA_CODES.get(area)
            if not code:
                logger.warning("楽待: エリアコード不明 '%s'、スキップします", area)
                continue
            props = self._search_area(code, area, min_yield, min_price, max_price)
            results.extend(props)
        return results

    def _search_area(
        self,
        area_code: str,
        area_name: str,
        min_yield: float,
        min_price: int | None,
        max_price: int | None,
    ) -> list[Property]:
        params: dict = {
            "area[]": area_code,
            "page": 1,
        }
        if min_yield:
            # 楽待の利回りフィルタ（7%以上なら "7"）
            params["rimawari_from"] = str(int(min_yield))
        if min_price:
            params["kakaku_from"] = str(min_price // 10000)  # 万円単位
        if max_price:
            params["kakaku_to"] = str(max_price // 10000)

        properties: list[Property] = []
        max_pages = 3  # 最大3ページ取得

        for page in range(1, max_pages + 1):
            params["page"] = page
            url = BASE_URL + "?" + urlencode(params, doseq=True)
            soup = self.fetch(url)
            if soup is None:
                break

            items = soup.select("div.bukken-list__item, li.property-list-item, article.property")
            if not items:
                # セレクタが変わった場合はより広い探索
                items = soup.select("[class*='property'], [class*='bukken']")

            if not items:
                logger.debug("楽待 %s page%d: 物件が見つかりません", area_name, page)
                break

            for item in items:
                prop = self._parse_item(item, area_name)
                if prop:
                    properties.append(prop)

            # 次ページがなければ終了
            if not soup.select("a.next, [class*='next']:not([class*='disabled'])"):
                break

        logger.info("楽待 %s: %d件取得", area_name, len(properties))
        return properties

    def _parse_item(self, item, area_name: str) -> Property | None:
        try:
            link_tag = item.select_one("a[href*='/syuuekibukkens/']")
            if not link_tag:
                return None
            href = link_tag.get("href", "")
            if not href.startswith("http"):
                href = "https://www.rakumachi.jp" + href

            raw_id = re.search(r"/(\d+)/?$", href)
            if not raw_id:
                return None
            prop_id = Property.unique_id(self.SOURCE, raw_id.group(1))

            title = (
                item.select_one("[class*='title'], [class*='name'], h2, h3")
                or link_tag
            )
            title_text = title.get_text(strip=True) if title else "（タイトル不明）"

            # 価格
            price_tag = item.select_one("[class*='price'], [class*='kakaku']")
            price = self.parse_price(price_tag.get_text()) if price_tag else None

            # 利回り
            yield_tag = item.select_one("[class*='yield'], [class*='rimawari']")
            yield_rate = self.parse_yield(yield_tag.get_text()) if yield_tag else None

            # 住所
            addr_tag = item.select_one("[class*='address'], [class*='location']")
            address = addr_tag.get_text(strip=True) if addr_tag else ""

            # 築年数
            age_tag = item.select_one("[class*='age'], [class*='chiku']")
            building_age = self.parse_age(age_tag.get_text()) if age_tag else None

            return Property(
                id=prop_id,
                source=self.SOURCE,
                title=title_text,
                url=href,
                price=price,
                yield_rate=yield_rate,
                area=area_name,
                address=address,
                building_age=building_age,
            )
        except Exception as e:
            logger.debug("楽待 parse error: %s", e)
            return None
