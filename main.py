#!/usr/bin/env python3
"""民泊物件自動検索・通知スクリプト"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path
import yaml

from scrapers import SuumoScraper, AtHomeScraper, HomesScraper, RakumachiScraper, ReinsScraper
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


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(dry_run: bool = False, force: bool = False, no_reins: bool = False) -> int:
    config = load_config()
    search_cfg = config.get("search", {})

    scrapers = [
        *([] if no_reins else [ReinsScraper(search_cfg)]),  # ログイン物件（担保・面積情報が豊富）
        RakumachiScraper(search_cfg),
        SuumoScraper(search_cfg),
        AtHomeScraper(search_cfg),
        HomesScraper(search_cfg),
    ]

    # 全サイトから物件を収集
    all_properties = []
    for scraper in scrapers:
        logger.info("=== %s 検索開始 ===", scraper.SOURCE)
        try:
            props = scraper.search()
            logger.info("%s: %d件取得", scraper.SOURCE, len(props))
            all_properties.extend(props)
        except Exception as e:
            logger.error("%s 検索エラー: %s", scraper.SOURCE, e)

    logger.info("合計取得: %d件", len(all_properties))

    # 評価・フィルタリング
    candidates = filter_properties(all_properties, config)
    logger.info("条件一致: %d件", len(candidates))

    # 既見物件を除外（--force で全件通知）
    seen = load_seen()
    if force:
        new_props = candidates
        logger.info("--force: 全件通知 (%d件)", len(new_props))
    else:
        new_props = filter_new(candidates, seen)
        logger.info("新着: %d件", len(new_props))

    if not new_props:
        logger.info("新着物件なし。通知をスキップします。")
        return 0

    # 通知
    if dry_run:
        logger.info("=== DRY RUN: 以下の物件を通知予定 ===")
        for p in new_props:
            logger.info(
                "  [%s] %s / %s / スコア%d点 / %s",
                p.source, p.title,
                f"利回り{p.yield_rate:.1f}%" if p.yield_rate else "利回り不明",
                p.score, p.url,
            )
    else:
        success = send_notification(new_props, config)
        if not success:
            logger.error("通知送信に失敗しました")
            return 1

    # 状態を保存
    updated_seen = mark_seen(new_props, seen)
    save_seen(updated_seen)
    logger.info("状態を保存しました（累計 %d件記録済み）", len(updated_seen))
    return 0


def main():
    parser = argparse.ArgumentParser(description="民泊物件自動検索・通知")
    parser.add_argument("--dry-run", action="store_true", help="通知せずに結果を表示")
    parser.add_argument("--force", action="store_true", help="既見物件も含めて通知")
    parser.add_argument("--no-reins", action="store_true", help="REINSをスキップ（認証不要で実行）")
    args = parser.parse_args()

    sys.exit(run(dry_run=args.dry_run, force=args.force, no_reins=args.no_reins))


if __name__ == "__main__":
    main()
