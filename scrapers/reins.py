from __future__ import annotations
import logging
import os
import re
import time
from typing import Optional
from .base import BaseScraper, Property

logger = logging.getLogger(__name__)

# 東日本・近畿圏 REINS システム URL
REINS_SYSTEMS = {
    "higashi": {
        "login_url": "https://system.reins.jp/login/GKB01001.do",
        "search_url": "https://system.reins.jp/search/GKC01001.do",
        "label": "東日本レインズ",
    },
    "kinki": {
        "login_url": "https://www.kinkireins.or.jp/kinki/user/login.do",
        "search_url": "https://www.kinkireins.or.jp/kinki/bukken/search.do",
        "label": "近畿圏レインズ",
    },
}

# エリア → REINS システムのマッピング
AREA_TO_SYSTEM = {
    "北海道": "higashi", "青森県": "higashi", "岩手県": "higashi",
    "宮城県": "higashi", "秋田県": "higashi", "山形県": "higashi",
    "福島県": "higashi", "茨城県": "higashi", "栃木県": "higashi",
    "群馬県": "higashi", "埼玉県": "higashi", "千葉県": "higashi",
    "東京都": "higashi", "神奈川県": "higashi", "新潟県": "higashi",
    "山梨県": "higashi", "長野県": "higashi",
    "滋賀県": "kinki", "京都府": "kinki", "大阪府": "kinki",
    "兵庫県": "kinki", "奈良県": "kinki", "和歌山県": "kinki",
}


class ReinsScraper(BaseScraper):
    """
    REINS（レインズ）スクレイパー
    認証が必要なため Selenium を使用。
    GitHub Secrets: REINS_USER, REINS_PASSWORD
    """
    SOURCE = "reins"
    REQUEST_DELAY = 3.0

    def __init__(self, config: dict):
        super().__init__(config)
        self.user = os.environ.get("REINS_USER", "")
        self.password = os.environ.get("REINS_PASSWORD", "")
        self._driver = None

    def search(self) -> list[Property]:
        if not self.user or not self.password:
            logger.warning("REINS: REINS_USER/REINS_PASSWORD が未設定。スキップします。")
            return []

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
        except ImportError:
            logger.error("REINS: selenium がインストールされていません。スキップします。")
            return []

        areas = self.config.get("areas", ["東京都"])
        # 必要なシステムを特定（重複排除）
        systems_needed = set()
        for area in areas:
            sys_key = AREA_TO_SYSTEM.get(area)
            if sys_key:
                systems_needed.add(sys_key)

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        results: list[Property] = []
        try:
            self._driver = webdriver.Chrome(options=opts)
            for sys_key in systems_needed:
                target_areas = [a for a in areas if AREA_TO_SYSTEM.get(a) == sys_key]
                props = self._search_system(sys_key, target_areas)
                results.extend(props)
        except Exception as e:
            logger.error("REINS ブラウザエラー: %s", e)
        finally:
            if self._driver:
                self._driver.quit()
                self._driver = None

        return results

    def _search_system(self, sys_key: str, areas: list[str]) -> list[Property]:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait, Select
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException

        info = REINS_SYSTEMS[sys_key]
        driver = self._driver
        wait = WebDriverWait(driver, 15)

        # --- ログイン ---
        try:
            driver.get(info["login_url"])
            time.sleep(2)

            # ユーザーID入力（idやname属性は実際のサイトに合わせて調整）
            for id_selector in ["userId", "loginId", "id", "user_id", "username"]:
                try:
                    uid_input = driver.find_element(By.NAME, id_selector)
                    uid_input.clear()
                    uid_input.send_keys(self.user)
                    break
                except NoSuchElementException:
                    continue

            # パスワード入力
            for pw_selector in ["password", "passwd", "pass", "userPassword"]:
                try:
                    pw_input = driver.find_element(By.NAME, pw_selector)
                    pw_input.clear()
                    pw_input.send_keys(self.password)
                    break
                except NoSuchElementException:
                    continue

            # ログインボタン
            for btn_selector in [
                "//input[@type='submit']",
                "//button[@type='submit']",
                "//input[@value='ログイン']",
                "//button[contains(text(),'ログイン')]",
            ]:
                try:
                    btn = driver.find_element(By.XPATH, btn_selector)
                    btn.click()
                    break
                except NoSuchElementException:
                    continue

            time.sleep(3)

            # ログイン成功確認
            if "login" in driver.current_url.lower():
                logger.error("REINS %s: ログイン失敗（URLが変わらず）", info["label"])
                return []

            logger.info("REINS %s: ログイン成功", info["label"])

        except Exception as e:
            logger.error("REINS %s ログインエラー: %s", info["label"], e)
            return []

        # --- 検索 ---
        properties: list[Property] = []
        max_price = self.config.get("max_price")
        min_price = self.config.get("min_price")
        min_yield = self.config.get("min_yield", 0)

        try:
            driver.get(info["search_url"])
            time.sleep(2)

            # 収益物件・一棟売りを選択（実際のフォームに合わせて調整）
            for sel_name in ["bukkenSyubetsu", "type", "propertyType"]:
                try:
                    sel = Select(driver.find_element(By.NAME, sel_name))
                    # 収益物件に相当する選択肢を選ぶ
                    for opt_text in ["収益物件", "一棟マンション", "一棟アパート", "アパート"]:
                        try:
                            sel.select_by_visible_text(opt_text)
                            break
                        except Exception:
                            continue
                    break
                except NoSuchElementException:
                    continue

            # 価格入力
            if max_price:
                for name in ["kakakuTo", "priceMax", "price_to"]:
                    try:
                        el = driver.find_element(By.NAME, name)
                        el.clear()
                        el.send_keys(str(max_price // 10000))
                        break
                    except NoSuchElementException:
                        continue
            if min_price:
                for name in ["kakakuFrom", "priceMin", "price_from"]:
                    try:
                        el = driver.find_element(By.NAME, name)
                        el.clear()
                        el.send_keys(str(min_price // 10000))
                        break
                    except NoSuchElementException:
                        continue

            # 検索ボタン
            for sel in [
                "//input[@type='submit']",
                "//button[@type='submit']",
                "//input[@value='検索']",
                "//button[contains(text(),'検索')]",
            ]:
                try:
                    driver.find_element(By.XPATH, sel).click()
                    break
                except NoSuchElementException:
                    continue

            time.sleep(3)

            # 結果パース（最大3ページ）
            for page in range(1, 4):
                page_props = self._parse_results(driver, areas)
                properties.extend(page_props)

                # 次ページ
                try:
                    next_btn = driver.find_element(
                        By.XPATH,
                        "//a[contains(text(),'次') or contains(text(),'次へ') or contains(@class,'next')]"
                    )
                    if not next_btn.is_enabled():
                        break
                    next_btn.click()
                    time.sleep(2)
                except NoSuchElementException:
                    break

        except Exception as e:
            logger.error("REINS %s 検索エラー: %s", info["label"], e)

        logger.info("REINS %s: %d件取得", info["label"], len(properties))
        return properties

    def _parse_results(self, driver, areas: list[str]) -> list[Property]:
        from selenium.webdriver.common.by import By
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(driver.page_source, "lxml")
        props = []

        # 物件行を探す（tableまたはlist形式）
        rows = (
            soup.select("tr.bukken-row, tr[class*='result'], tr[id*='bukken']")
            or soup.select("div[class*='result-item'], li[class*='property']")
        )

        for row in rows:
            try:
                # リンク取得
                link = row.select_one("a[href]")
                if not link:
                    continue
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = driver.current_url.rsplit("/", 1)[0] + "/" + href.lstrip("/")

                raw_id = re.search(r"[?&](?:id|bukkenNo|no)=(\w+)", href)
                if not raw_id:
                    raw_id = re.search(r"/(\d+)/?(?:\?|$)", href)
                prop_id = Property.unique_id(self.SOURCE, raw_id.group(1) if raw_id else href[-16:])

                title = link.get_text(strip=True) or "REINS物件"

                text = row.get_text(" ", strip=True)
                price = self.parse_price(text)
                yield_rate = self.parse_yield(text)
                building_age = self.parse_age(text)

                # 土地面積・延床面積を取得（担保評価に使用）
                land_m = re.search(r"土地[面積]?\s*[:：]?\s*(\d+(?:\.\d+)?)\s*m", text)
                floor_m = re.search(r"延床[面積]?\s*[:：]?\s*(\d+(?:\.\d+)?)\s*m", text)
                land_area = float(land_m.group(1)) if land_m else None
                floor_area = float(floor_m.group(1)) if floor_m else None

                addr_tag = row.select_one("[class*='address'], [class*='location'], td:nth-child(3)")
                address = addr_tag.get_text(strip=True) if addr_tag else ""
                area_name = next((a for a in areas if a in address), areas[0] if areas else "")

                props.append(Property(
                    id=prop_id,
                    source=self.SOURCE,
                    title=title,
                    url=href,
                    price=price,
                    yield_rate=yield_rate,
                    area=area_name,
                    address=address,
                    building_age=building_age,
                    land_area=land_area,
                    floor_area=floor_area,
                    extra={"raw_text": text[:300]},
                ))
            except Exception as e:
                logger.debug("REINS row parse error: %s", e)

        return props
