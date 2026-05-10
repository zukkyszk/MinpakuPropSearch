from __future__ import annotations
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date
from scrapers.base import Property

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    "rakumachi": "楽待",
    "suumo": "SUUMO",
    "athome": "AtHome",
    "homes": "HOME'S",
    "reins": "REINS",
}


def _format_price(yen: int | None) -> str:
    if yen is None:
        return "不明"
    if yen >= 1_0000_0000:
        oku = yen // 1_0000_0000
        man = (yen % 1_0000_0000) // 10000
        return f"{oku}億{man:,}万円" if man else f"{oku}億円"
    return f"{yen // 10000:,}万円"


def _surplus_label(pct: float | None) -> str:
    if pct is None:
        return "算出不可"
    color = "#388e3c" if pct >= 0 else "#d32f2f"
    sign = "+" if pct >= 0 else ""
    return f'<span style="color:{color};font-weight:bold">{sign}{pct:.1f}%</span>'


def _score_color(score: int) -> str:
    if score >= 70:
        return "#d32f2f"
    if score >= 50:
        return "#388e3c"
    return "#666"


def _build_html(properties: list[Property], prefix: str) -> str:
    today = date.today().strftime("%Y年%m月%d日")
    rows = ""
    for i, p in enumerate(properties, 1):
        source_label = SOURCE_LABELS.get(p.source, p.source)
        ev = p.extra.get("asset_eval", {})

        collateral_val = ev.get("collateral_value")
        surplus_pct = ev.get("collateral_surplus_pct")
        res_yield = ev.get("residential_yield")
        land_price_m2 = ev.get("land_price_m2")
        data_src = ev.get("data_source", "")

        collateral_str = _format_price(collateral_val) if collateral_val else "算出不可"
        surplus_str = _surplus_label(surplus_pct)
        res_yield_str = f"{res_yield:.1f}%" if res_yield else "算出不可"
        land_price_str = (
            f"{land_price_m2 // 10_000:,}万円/m²"
            if land_price_m2 else "不明"
        )
        src_badge = (
            '<span style="font-size:10px;color:#999">(実取引)</span>'
            if data_src == "mlit_api" else
            '<span style="font-size:10px;color:#999">(概算)</span>'
        )

        rows += f"""
        <tr style="background:{'#f9f9f9' if i % 2 == 0 else '#ffffff'}">
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">{i}</td>
          <td style="padding:8px;border:1px solid #ddd;min-width:160px;">
            <a href="{p.url}" style="color:#1a73e8;font-weight:bold;">{p.title}</a><br>
            <span style="font-size:12px;color:#666;">{p.address or p.area}</span>
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;white-space:nowrap;">
            <span style="background:#e3f2fd;padding:2px 6px;border-radius:4px;font-size:12px;">
              {source_label}
            </span>
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:right;white-space:nowrap;">
            {_format_price(p.price)}
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">
            {f"{p.yield_rate:.1f}%" if p.yield_rate else "不明"}
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">
            {f"築{p.building_age}年" if p.building_age else "不明"}
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:right;white-space:nowrap;">
            {collateral_str}<br>
            <span style="font-size:11px;">余力:{surplus_str}</span>
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">
            {res_yield_str}
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:right;white-space:nowrap;">
            {land_price_str}{src_badge}
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">
            <strong style="font-size:16px;color:{_score_color(p.score)}">
              {p.score}点
            </strong>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>民泊物件通知</title>
  <style>
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; max-width: 1100px; margin: auto; padding: 20px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th {{ background: #1a73e8; color: white; padding: 8px; border: 1px solid #ddd; white-space: nowrap; }}
  </style>
</head>
<body>
  <h2 style="border-left:4px solid #1a73e8;padding-left:12px;">
    {prefix} 新着物件レポート（{today}）
  </h2>
  <p>本日の新着物件 <strong>{len(properties)}件</strong> をお知らせします。</p>

  <h3 style="font-size:13px;color:#666;margin-bottom:4px;">スコア基準</h3>
  <p style="font-size:12px;color:#888;margin-top:0">
    総合スコア 100点 = 資産性（担保余力+居住用利回り）50点 + 民泊利回り25点 + 価格帯10点 + 築年数10点 + エリア5点<br>
    担保余力 = (担保評価額 − 物件価格) ÷ 物件価格 ×100。プラスなら「担保余力あり」。
  </p>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>物件名・所在地</th>
        <th>サイト</th>
        <th>物件価格</th>
        <th>民泊利回り</th>
        <th>築年数</th>
        <th>担保評価額</th>
        <th>居住用利回り</th>
        <th>土地単価</th>
        <th>総合スコア</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <p style="margin-top:24px;font-size:11px;color:#aaa;">
    ・担保評価額は路線価/公示地価(国土交通省API)を基に試算した概算値です（土地×80% + 建物×70%）。<br>
    ・居住用利回りはエリア平均賃料×延床面積から試算した推定値です。<br>
    ・このメールは MinpakuPropSearch が自動送信しています。
  </p>
</body>
</html>"""


def send_notification(properties: list[Property], config: dict) -> bool:
    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    notify_to = os.environ.get("NOTIFY_TO_EMAIL", gmail_user)

    if not gmail_user or not gmail_password:
        logger.error("GMAIL_USER または GMAIL_APP_PASSWORD が未設定です")
        return False

    prefix = config.get("notification", {}).get("subject_prefix", "[民泊物件]")
    today = date.today().strftime("%Y/%m/%d")
    subject = f"{prefix} 新着{len(properties)}件 ({today})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = notify_to

    # プレーンテキスト
    plain_lines = [f"民泊物件 新着通知 {today}", f"新着 {len(properties)}件", ""]
    for i, p in enumerate(properties, 1):
        ev = p.extra.get("asset_eval", {})
        source_label = SOURCE_LABELS.get(p.source, p.source)
        surplus = ev.get("collateral_surplus_pct")
        surplus_str = f"{'+' if surplus and surplus >= 0 else ''}{surplus:.1f}%" if surplus is not None else "不明"
        plain_lines.append(
            f"{i}. [{source_label}] {p.title}\n"
            f"   価格: {_format_price(p.price)} / 民泊利回り: {f'{p.yield_rate:.1f}%' if p.yield_rate else '不明'}\n"
            f"   担保余力: {surplus_str} / 居住用利回り: "
            + (f"{ev.get('residential_yield'):.1f}%" if ev.get('residential_yield') else "不明") + "\n"
            f"   スコア: {p.score}点 / {p.address or p.area}\n"
            f"   {p.url}"
        )
    msg.attach(MIMEText("\n".join(plain_lines), "plain", "utf-8"))

    html_content = _build_html(properties, prefix)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_password)
            smtp.sendmail(gmail_user, notify_to, msg.as_string())
        logger.info("メール送信完了: %s → %s (%d件)", gmail_user, notify_to, len(properties))
        return True
    except Exception as e:
        logger.error("メール送信失敗: %s", e)
        return False
