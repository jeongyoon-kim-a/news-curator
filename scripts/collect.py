"""
수집 모듈
=========
sources.yaml에 정의된 매체에서 RSS / Google News 검색으로 기사를 수집한다.

각 기사는 다음 dict 구조로 반환:
{
    "title": str,
    "link": str,
    "summary": str,        # description / content snippet
    "published": datetime, # UTC aware
    "source_key": str,     # sources.yaml의 키
    "source_name": str,    # 사람 읽을 이름
    "source_weight": int,  # 매체 가중치
}
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import quote_plus

import feedparser  # type: ignore
import yaml

log = logging.getLogger(__name__)

# Google News RSS 검색 템플릿
# hl=ko, gl=KR, ceid=KR:ko 로 한국어 우선; 영문 매체는 영어로 자동 처리됨
_GNEWS_TEMPLATE = (
    "https://news.google.com/rss/search?"
    "q={query}+site%3A{site}&hl=ko&gl=KR&ceid=KR%3Ako"
)


def _parse_dt(entry) -> datetime:
    """feedparser entry에서 datetime 추출. 실패하면 현재 시각."""
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            try:
                return datetime(*struct[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return datetime.now(timezone.utc)


def _clean_html(text: str) -> str:
    """summary 필드의 HTML 태그 제거."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fetch_rss(url: str) -> list:
    """일반 RSS 피드 fetch."""
    try:
        parsed = feedparser.parse(url)
        if parsed.bozo and not parsed.entries:
            log.warning("RSS parse error for %s: %s", url, parsed.bozo_exception)
        return parsed.entries
    except Exception as e:  # noqa: BLE001
        log.warning("RSS fetch failed for %s: %s", url, e)
        return []


def _fetch_gnews(site: str, query: str = "") -> list:
    """Google News RSS로 특정 사이트 기사 검색."""
    # query 비어있어도 site만으로 최근 기사 가져옴
    q = quote_plus(query) if query else "news"
    url = _GNEWS_TEMPLATE.format(query=q, site=site)
    return _fetch_rss(url)


def _entry_to_article(entry, source_key: str, meta: dict) -> dict | None:
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip()
    if not title or not link:
        return None

    summary = _clean_html(
        entry.get("summary")
        or entry.get("description")
        or (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
    )

    return {
        "title": title,
        "link": link,
        "summary": summary[:500],  # 너무 길면 자름
        "published": _parse_dt(entry),
        "source_key": source_key,
        "source_name": meta["name"],
        "source_weight": meta["weight"],
    }


def collect_all(sources_path: str) -> list[dict]:
    """sources.yaml 전체를 돌며 기사를 모은다."""
    with open(sources_path, "r", encoding="utf-8") as f:
        sources = yaml.safe_load(f)

    articles: list[dict] = []
    for region, items in sources.items():
        for source_key, meta in items.items():
            log.info("Fetching %s / %s", region, source_key)
            entries: Iterable
            if meta["type"] == "rss":
                entries = _fetch_rss(meta["url"])
            elif meta["type"] == "gnews":
                entries = _fetch_gnews(meta["site"])
            else:
                log.warning("Unknown source type: %s", meta["type"])
                continue

            count = 0
            for entry in entries:
                article = _entry_to_article(entry, source_key, meta)
                if article:
                    articles.append(article)
                    count += 1
            log.info("  → %d articles", count)

    log.info("Total raw articles: %d", len(articles))
    return _dedupe(articles)


def _dedupe(articles: list[dict]) -> list[dict]:
    """제목이 거의 동일한 기사 제거. Google News + 원본 RSS 중복 흔함."""
    seen: dict[str, dict] = {}
    for art in articles:
        # 정규화: 공백 압축, 소문자, 특수문자 제거
        norm = re.sub(r"[^\w가-힣]+", "", art["title"].lower())
        if not norm:
            continue
        # 동일 제목이면 매체 가중치 높은 쪽 유지 (1차 보도 우선)
        existing = seen.get(norm)
        if existing is None or art["source_weight"] > existing["source_weight"]:
            seen[norm] = art
    log.info("After dedupe: %d articles", len(seen))
    return list(seen.values())
