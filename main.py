#!/usr/bin/env python3
"""民泊物件自動検索・通知スクリプト"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
import yaml

from scrapers import SuumoScraper, AtHomeScraper, HomesScraper, RakumachiScraper, ReinsScraper
from scrapers.base import BaseScraper, Property
from evaluator import filter_properties
from state import load_seen, save_seen, filter_new, mark_seen
from notifier import send_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"
SCRAPER_CLASSES = [ReinsScraper, RakumachiScraper, SuumoScraper, AtHomeScraper, HomesScraper]


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_profiles(config: dict) -> list[dict]:
    """
    設定から検索プロファイルのリストを返す。
    - searches: [...]  複数プロファイル形式
    - search: {...}    旧来の単一形式（後方互換）
    """
    if "searches" in config:
        return config["searches"]
    if "search" in config:
        return [config["search"]]
    return [{}]


def _dedup(properties: list[Property]) -> list[Property]:
    """同じ ID の物件が複数プロファイルで重複した場合、スコアが高い方を残す"""
    best: dict[str, Property] = {}
    for p in properties:
        if p.id not in best or p.score > best[p.id].score:
            best[p.id] = p
    return list(best.values())


def run(dry_run: bool = False, force: bool = False, no_reins: bool = False) -> int:
    config = load_config()
    profiles = get_profiles(config)
    eval_cfg = config.get("evaluation", {})

    logger.info("検索プロファイル数: %d", len(profiles))

    all_candidates: list[Property] = []

    for profile in profiles:
        name = profile.get("name", "デフォルト")
        property_types = profile.get("property_types", [])
        logger.info("=== プロファイル「%s」開始（種別: %s）===",
                    name, "全種別" if not property_types else "/".join(property_types))

        scrapers = [
            *([] if no_reins else [ReinsScraper(profile)]),
            RakumachiScraper(profile),
            SuumoScraper(profile),
            AtHomeScraper(profile),
            HomesScraper(profile),
        ]

        raw: list[Property] = []
        for scraper in scrapers:
            logger.info("  [%s] %s 検索", name, scraper.SOURCE)
            try:
                props = scraper.search()
                logger.info("  [%s] %s: %d件取得", name, scraper.SOURCE, len(props))
                raw.extend(props)
            except Exception as e:
                logger.error("  [%s] %s エラー: %s", name, scraper.SOURCE, e)

        # 物件種別フィルタ
        if property_types:
            before = len(raw)
            raw = [p for p in raw if BaseScraper.match_property_types(p, property_types)]
            logger.info("  [%s] 種別フィルタ: %d件 → %d件", name, before, len(raw))

        # プロファイル名を物件に記録
        for p in raw:
            p.extra["profile"] = name

        # 評価・フィルタ（プロファイルの条件を使う）
        profile_config = {"search": profile, "evaluation": eval_cfg}
        candidates = filter_properties(raw, profile_config)
        logger.info("  [%s] スコア通過: %d件", name, len(candidates))
        all_candidates.extend(candidates)

    # 複数プロファイルで重複した物件はスコアが高い方を残す
    all_candidates = _dedup(all_candidates)
    all_candidates.sort(key=lambda p: p.score, reverse=True)
    logger.info("合計候補: %d件（重複除去済み）", len(all_candidates))

    # 既見物件を除外（--force で全件通知）
    seen = load_seen()
    if force:
        new_props = all_candidates
        logger.info("--force: 全件通知 (%d件)", len(new_props))
    else:
        new_props = filter_new(all_candidates, seen)
        logger.info("新着: %d件", len(new_props))

    if not new_props:
        logger.info("新着物件なし。通知をスキップします。")
        return 0

    if dry_run:
        logger.info("=== DRY RUN: 以下の物件を通知予定 ===")
        for p in new_props:
            logger.info(
                "  [%s|%s] %s / %s / スコア%d点",
                p.extra.get("profile", "-"), p.source, p.title,
                f"利回り{p.yield_rate:.1f}%" if p.yield_rate else "利回り不明",
                p.score,
            )
    else:
        success = send_notification(new_props, config)
        if not success:
            logger.error("通知送信に失敗しました")
            return 1

    updated_seen = mark_seen(new_props, seen)
    save_seen(updated_seen)
    logger.info("状態を保存しました（累計 %d件記録済み）", len(updated_seen))
    return 0


def main():
    parser = argparse.ArgumentParser(description="民泊物件自動検索・通知")
    parser.add_argument("--dry-run", action="store_true", help="通知せずに結果を表示")
    parser.add_argument("--force", action="store_true", help="既見物件も含めて通知")
    parser.add_argument("--no-reins", action="store_true", help="REINSをスキップ")
    args = parser.parse_args()

    sys.exit(run(dry_run=args.dry_run, force=args.force, no_reins=args.no_reins))


if __name__ == "__main__":
    main()
