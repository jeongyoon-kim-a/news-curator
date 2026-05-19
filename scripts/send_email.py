"""
데일리 큐레이션 이메일 발송
=========================
data/daily.json을 읽어서 HTML 이메일로 정리해 Resend로 발송한다.

환경변수:
  RESEND_API_KEY    Resend API 키
  RECIPIENT_EMAIL   받을 사람 이메일
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import urllib.request
import urllib.error


KST = timezone(timedelta(hours=9))


def load_data() -> dict:
    repo_root = Path(__file__).resolve().parent.parent
    with open(repo_root / "data" / "daily.json", "r", encoding="utf-8") as f:
        return json.load(f)


def format_time_ago_kst(iso_str: str) -> str:
    """KST 기준 'N시간 전' 표시."""
    then = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delta = now - then
    hours = int(delta.total_seconds() / 3600)
    if hours < 1:
        mins = int(delta.total_seconds() / 60)
        return f"{mins}분 전"
    return f"{hours}시간 전"


def event_label_ko(label: str) -> str:
    mapping = {
        "m_and_a": "M&A",
        "earnings": "실적",
        "regulation": "규제",
        "exec_change": "임원교체",
        "funding": "투자/IPO",
    }
    return mapping.get(label, label)


def render_html(data: dict) -> str:
    generated = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
    generated_kst = generated.astimezone(KST)
    date_str = generated_kst.strftime("%Y년 %m월 %d일")
    total = data["total_articles"]

    blocks = []
    for cat_key, cat in data["categories"].items():
        if not cat["articles"]:
            continue
        cat_html = f"""
        <h2 style="font-size:16px;font-weight:600;color:#2a2620;margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid #e8e3d8;">
            {cat['display_name']} <span style="font-size:11px;color:#b8af9f;font-weight:400;">({cat['count']}건)</span>
        </h2>
        """
        article_blocks = []
        for art in cat["articles"]:
            events = " ".join(
                f'<span style="display:inline-block;font-size:10px;padding:2px 7px;border-radius:10px;background:#faf8f3;color:#8a8175;border:1px solid #e8e3d8;margin-right:4px;">{event_label_ko(l)}</span>'
                for l in art.get("event_labels", [])
            )
            summary = (art.get("summary", "") or "")[:200]
            article_html = f"""
            <div style="border:1px solid #e8e3d8;border-radius:8px;padding:14px 16px;margin-bottom:10px;background:#ffffff;">
                <div style="font-size:11px;color:#8a8175;margin-bottom:6px;">
                    <span style="font-weight:500;">{art['source_name']}</span>
                    <span style="color:#b8af9f;margin-left:8px;">{format_time_ago_kst(art['published'])}</span>
                </div>
                <div style="margin-bottom:6px;">
                    <a href="{art['link']}" style="color:#2a2620;font-size:14px;font-weight:500;text-decoration:none;line-height:1.5;">{art['title']}</a>
                </div>
                {f'<div style="font-size:12px;color:#8a8175;line-height:1.55;margin-bottom:8px;">{summary}{"..." if len(art.get("summary", "")) > 200 else ""}</div>' if summary else ""}
                <div>{events}</div>
            </div>
            """
            article_blocks.append(article_html)
        blocks.append(cat_html + "\n".join(article_blocks))

    body = "\n".join(blocks)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#faf8f3;font-family:-apple-system,BlinkMacSystemFont,'Pretendard',sans-serif;color:#2a2620;">
    <div style="max-width:680px;margin:0 auto;padding:30px 24px;">
        <div style="text-align:center;margin-bottom:24px;">
            <h1 style="font-size:24px;font-weight:500;letter-spacing:-0.02em;margin:0 0 6px;">오늘의 큐레이션</h1>
            <p style="font-size:12px;color:#8a8175;margin:0;">{date_str} · 총 {total}건</p>
        </div>
        {body}
        <p style="font-size:11px;color:#b8af9f;text-align:center;margin:40px 0 0;">News Curator · 매일 새벽 6시 자동 발송</p>
    </div>
</body>
</html>
"""


def send_email(html: str, recipient: str, api_key: str, subject: str) -> None:
    """Resend API로 이메일 발송."""
    url = "https://api.resend.com/emails"
    payload = json.dumps({
        "from": "News Curator <onboarding@resend.dev>",
        "to": [recipient],
        "subject": subject,
        "html": html,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            resp_body = response.read().decode("utf-8")
            print(f"✓ Email sent. Resend response: {resp_body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"✗ Resend API error {e.code}: {body}", file=sys.stderr)
        raise


def main() -> int:
    api_key = os.environ.get("RESEND_API_KEY")
    recipient = os.environ.get("RECIPIENT_EMAIL")
    if not api_key or not recipient:
        print("✗ RESEND_API_KEY or RECIPIENT_EMAIL missing", file=sys.stderr)
        return 1

    data = load_data()
    if data["total_articles"] == 0:
        print("No articles today. Skipping email.")
        return 0

    html = render_html(data)
    today_kst = datetime.now(KST).strftime("%m/%d")
    subject = f"[큐레이션] {today_kst} · {data['total_articles']}건"
    send_email(html, recipient, api_key, subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
