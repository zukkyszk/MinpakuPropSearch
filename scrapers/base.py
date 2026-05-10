from __future__ import annotations
import re
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class Property:
    id: str
    source: str
    title: str
    url: str
    price: Optional[int] = None          # 円
    yield_rate: Optional[float] = None   # 表面利回り (%)
    area: str = ""
    address: str = ""
    building_age: Optional[int] = None   # 築年数
    building_type: str = ""
    floor_area: Optional[float] = None   # 専有面積 (m²)
    land_area: Optional[float] = None    # 土地面積 (m²)
    description: str = ""
    score: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def unique_id(source: str, raw_id: str) -> str:
        return f"{source}_{raw_id}"


class BaseScraper:
    SOURCE = ""
    REQUEST_DELAY = 2.0  # 礼儀として各リクエスト間に待機

    def __init__(self, config: dict):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch(self, url: str, **kwargs) -> Optional[BeautifulSoup]:
        try:
            time.sleep(self.REQUEST_DELAY)
            resp = self.session.get(url, timeout=20, **kwargs)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            return BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.warning("fetch failed [%s]: %s", url, e)
            return None

    def search(self) -> list[Property]:
        raise NotImplementedError

    @staticmethod
    def parse_price(text: str) -> Optional[int]:
        """'5,500万円' や '3億2000万円' などを円の整数に変換"""
        text = text.replace(",", "").replace(" ", "").replace("　", "")
        oku = re.search(r"(\d+(?:\.\d+)?)億", text)
        man = re.search(r"(\d+(?:\.\d+)?)万", text)
        price = 0
        if oku:
            price += int(float(oku.group(1)) * 1_0000_0000)
        if man:
            price += int(float(man.group(1)) * 10000)
        return price if price > 0 else None

    @staticmethod
    def parse_yield(text: str) -> Optional[float]:
        """'8.50%' を float に変換"""
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        return float(m.group(1)) if m else None

    @staticmethod
    def parse_age(text: str) -> Optional[int]:
        """'築15年' を int に変換"""
        m = re.search(r"築(\d+)年", text)
        return int(m.group(1)) if m else None
