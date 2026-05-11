from __future__ import annotations
import logging
import re
from urllib.parse import urlencode
from .base import BaseScraper, Property
from areas import group_by_pref, address_in_area

logger = logging.getLogger(__name__)

# SUUMO 収益物件 都道府県コード
PREF_CODES = {
    "北海道": "01", "青森県": "02", "岩手県": "03", "宮城県": "04",
    "秋田県": "05", "山形県": "06", "福島県": "07", "茨城県": "08",
    "栃木県": "09", "群馬県": "10", "埼玉県": "11", "千葉県": "12",
    "東京都": "13", "神奈川県": "14", "新潟県": "15", "富山県": "16",
    "石川県": "17", "福井県": "18", "山梨県": "19", "長野県": "20",
    "岐阜県": "21", "静岡県": "22", "愛知県": "23", "三重県": "24",
    "滋賀県": "25", "京都府": "26", "大阪府": "27", "兵庫県": "28",
    "奈良県": "29", "和歌山県": "30", "福岡県": "40", "沖縄県": "47",
}

BASE_URL = "https://suumo.jp/library/"


class SuumoScraper(BaseScraper):
    SOURCE = "suumo"

    def search(self) -> list[Property]:
        areas = self.config.get("areas", ["東京都"])
        results: list[Property] = []
        for pref, filter_keys in group_by_pref(areas).items():
            code = PREF_CODES.get(pref)
            if not code:
                logger.warning("SUUMO: 都道府県コード不明 '%s'、スキップします", pref)
                continue
            props = self._search_pref(code, pref)
            if None not in filter_keys:
                props = [p for p in props if address_in_area(p.address, filter_keys)]
            results.extend(props)
        return results

    def _search_pref(
        self,
        pref_code: str,
        area_name: str,
    ) -> list[Property]:
        # SUUMO物件ライブラリー: 都道府県単位で建物一覧を取得
        base = f"{BASE_URL}tf_{pref_code}/"
        properties: list[Property] = []
        max_pages = 3

        for page in range(1, max_pages + 1):
            page_url = base + (f"?page={page}" if page > 1 else "")
            soup = self.fetch(page_url)
            if soup is None:
                break

            items = soup.select(
                "div[class*='cassette'], "
                "div[class*='dottable'], "
                "li[class*='cassette'], "
                "article[class*='property']"
            )
            if not items:
                logger.debug("SUUMO %s page%d: 物件が見つかりません", area_name, page)
                break

            for item in items:
                prop = self._parse_item(item, area_name)
                if prop:
                    properties.append(prop)

            if not soup.select("a.pagination-parts[aria-label='次へ'], .pagination .next, a[rel='next']"):
                break

        logger.info("SUUMO %s: %d件取得", area_name, len(properties))
        return properties

    def _parse_item(self, item, area_name: str) -> Property | None:
        try:
            link_tag = item.select_one("a[href*='/library/']")
            if not link_tag:
                link_tag = item.select_one("a[href*='suumo.jp']")
            if not link_tag:
                link_tag = item.select_one("a[href]")
            if not link_tag:
                return None
            href = link_tag.get("href", "")
            if not href.startswith("http"):
                href = "https://suumo.jp" + href

            raw_id = re.search(r"/(\d+)/?", href)
            if not raw_id:
                return None
            prop_id = Property.unique_id(self.SOURCE, raw_id.group(1))

            title_tag = item.select_one("h2, h3, [class*='title']")
            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)

            price_tag = item.select_one("[class*='price'], .dottable-vm")
            price = self.parse_price(price_tag.get_text()) if price_tag else None

            yield_tag = item.select_one("[class*='yield'], [class*='rimawari'], .cassette-label-rimawari")
            yield_rate = self.parse_yield(yield_tag.get_text()) if yield_tag else None

            addr_tag = item.select_one("[class*='address'], [class*='location'], .dottable-bd")
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
            logger.debug("SUUMO parse error: %s", e)
            return None
