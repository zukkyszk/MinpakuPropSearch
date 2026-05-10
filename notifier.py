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
}


def _format_price(yen: int | None) -> str:
    if yen is None:
        return "不明"
    if yen >= 1_0000_0000:
        oku = yen // 1_0000_0000
        man = (yen % 1_0000_0000) // 10000
        return f"{oku}億{man:,}万円" if man else f"{oku}億円"
    return f"{yen // 10000:,}万円"


def _build_html(properties: list[Property], prefix: str) -> str:
    today = date.today().strftime("%Y年%m月%d日")
    rows = ""
    for i, p in enumerate(properties, 1):
        source_label = SOURCE_LABELS.get(p.source, p.source)
        rows += f"""
        <tr style="background:{'#f9f9f9' if i % 2 == 0 else '#ffffff'}">
          <td style="padding:8px;border:1px solid #ddd;">{i}</td>
          <td style="padding:8px;border:1px solid #ddd;">
            <a href="{p.url}" style="color:#1a73e8;">{p.title}</a>
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">{source_label}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:right;">{_format_price(p.price)}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">
            {f"{p.yield_rate:.1f}%" if p.yield_rate else "不明"}
          </td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">
            {f"築{p.building_age}年" if p.building_age else "不明"}
          </td>
          <td style="padding:8px;border:1px solid #ddd;">{p.address or p.area}</td>
          <td style="padding:8px;border:1px solid #ddd;text-align:center;">
            <strong style="color:{'#d32f2f' if p.score >= 70 else '#388e3c' if p.score >= 50 else '#666'}">
              {p.score}点
            </strong>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><title>民泊物件通知</title></head>
<body style="font-family:sans-serif;color:#333;max-width:1000px;margin:auto;padding:20px">
  <h2 style="border-left:4px solid #1a73e8;padding-left:12px;">
    {prefix} 新着物件レポート（{today}）
  </h2>
  <p>本日の新着物件 <strong>{len(properties)}件</strong> をお知らせします。</p>
  <table style="border-collapse:collapse;width:100%;font-size:14px;">
    <thead style="background:#1a73e8;color:white;">
      <tr>
        <th style="padding:8px;border:1px solid #ddd;">#</th>
        <th style="padding:8px;border:1px solid #ddd;">物件名</th>
        <th style="padding:8px;border:1px solid #ddd;">サイト</th>
        <th style="padding:8px;border:1px solid #ddd;">価格</th>
        <th style="padding:8px;border:1px solid #ddd;">利回り</th>
        <th style="padding:8px;border:1px solid #ddd;">築年数</th>
        <th style="padding:8px;border:1px solid #ddd;">所在地</th>
        <th style="padding:8px;border:1px solid #ddd;">スコア</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="margin-top:20px;font-size:12px;color:#999;">
    スコアは民泊適性を独自基準で評価したものです（100点満点）。<br>
    このメールは MinpakuPropSearch が自動送信しています。
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

    # プレーンテキスト（フォールバック）
    plain_lines = [f"民泊物件 新着通知 {today}", f"新着 {len(properties)}件", ""]
    for i, p in enumerate(properties, 1):
        source_label = SOURCE_LABELS.get(p.source, p.source)
        plain_lines.append(
            f"{i}. [{source_label}] {p.title}\n"
            f"   価格: {_format_price(p.price)} / 利回り: {f'{p.yield_rate:.1f}%' if p.yield_rate else '不明'}\n"
            f"   スコア: {p.score}点 / {p.address or p.area}\n"
            f"   {p.url}"
        )
    msg.attach(MIMEText("\n".join(plain_lines), "plain", "utf-8"))

    # HTML
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
