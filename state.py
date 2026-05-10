from __future__ import annotations
import json
import os
from pathlib import Path
from scrapers.base import Property

STATE_FILE = Path(__file__).parent / "seen_properties.json"


def load_seen() -> set[str]:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("ids", []))
    return set()


def save_seen(seen: set[str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"ids": sorted(seen)}, f, ensure_ascii=False, indent=2)


def filter_new(properties: list[Property], seen: set[str]) -> list[Property]:
    return [p for p in properties if p.id not in seen]


def mark_seen(properties: list[Property], seen: set[str]) -> set[str]:
    return seen | {p.id for p in properties}
