"""
스코어링 모듈
=============
rules.yaml에 정의된 룰에 따라 기사에 카테고리와 점수를 부여한다.

스코어링 로직:
  1. 카테고리 매칭: 제목+요약에서 카테고리 키워드 검색
     - 매칭된 카테고리들 중 점수가 가장 높은 카테고리로 배정
     - 어디에도 안 걸리면 제외
  2. 점수 계산:
     base = keyword_score + source_weight + recency_score
         + event_bonus
         - noise_penalty
  3. min_score 미만은 탈락
  4. 카테고리별 상위 target_count개 선정 → 합쳐서 반환
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Iterable

import yaml

log = logging.getLogger(__name__)


# =====================================================================
# URL 블랙리스트
# =====================================================================
# 기사 link에 아래 패턴이 포함되면 카테고리/점수 계산 전에 자동 제외.
# 데일리 시황 영상, TV 코너, 팟캐스트 등 정형화된 노이즈 콘텐츠를 거르기 위함.
URL_BLACKLIST = [
    "/news/videos/",   # Bloomberg 영상 (Brief, The Close, Surveillance 등)
    "/television/",    # Bloomberg TV 코너
    "/audio/",         # 팟캐스트
    "/podcasts/",      # 팟캐스트 (다른 매체)
    "/live/",          # 라이브 방송
]


def _is_blacklisted_url(link: str) -> bool:
    """기사 URL이 블랙리스트 패턴에 해당하는지."""
    if not link:
        return False
    link_lower = link.lower()
    return any(pattern in link_lower for pattern in URL_BLACKLIST)


def _haystack(article: dict) -> str:
    """매칭 대상 텍스트 (제목 + 요약)."""
    return f"{article['title']} {article.get('summary', '')}".lower()


# 단어 경계 매칭용 정규식 캐시
_PATTERN_CACHE: dict[str, re.Pattern] = {}


def _word_pattern(kw: str) -> re.Pattern:
    """키워드를 단어 경계 매칭 정규식으로 변환. 결과는 캐시.

    - 영문/숫자 키워드: \\b 사용 (예: 'SEC'은 'AI sector'에 매칭 안 됨)
    - 한글 키워드: \\b가 한글에서는 잘 작동하지 않으므로 그대로 substring 매칭
      (한국어는 띄어쓰기 기반이 아니라 어절 단위라 SEC같은 오매칭 문제가 거의 없음)
    """
    if kw in _PATTERN_CACHE:
        return _PATTERN_CACHE[kw]

    # 한글이 포함된 키워드는 그냥 escape 후 substring 매칭
    has_korean = any('\uac00' <= c <= '\ud7a3' for c in kw)
    if has_korean:
        pattern = re.compile(re.escape(kw.lower()), re.IGNORECASE)
    else:
        # 영문/숫자: 단어 경계 \b 적용
        pattern = re.compile(r'\b' + re.escape(kw.lower()) + r'\b', re.IGNORECASE)
    _PATTERN_CACHE[kw] = pattern
    return pattern


def _count_matches(text: str, keywords: Iterable[str]) -> int:
    """텍스트에서 키워드가 매칭된 *키워드 개수* 반환. 단어 경계 인식."""
    matched = 0
    for kw in keywords:
        if _word_pattern(kw).search(text):
            matched += 1
    return matched


def _has_any(text: str, keywords: Iterable[str]) -> bool:
    return any(_word_pattern(kw).search(text) for kw in keywords)

def _recency_score(published: datetime, rules: dict) -> int:
    now = datetime.now(timezone.utc)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    hours = (now - published).total_seconds() / 3600
    cfg = rules["recency"]
    if hours <= 6:
        return cfg["within_6h"]
    if hours <= 12:
        return cfg["within_12h"]
    if hours <= 24:
        return cfg["within_24h"]
    if hours <= 48:
        return cfg["within_48h"]
    return cfg["older"]


def _event_bonus_score(text: str, rules: dict) -> tuple[int, list[str]]:
    """이벤트 보너스 총합과 매칭된 이벤트 라벨 반환."""
    total = 0
    labels = []
    for event_name, cfg in rules["event_bonus"].items():
        if _has_any(text, cfg["keywords"]):
            total += cfg["score"]
            labels.append(event_name)
    return total, labels


def _noise_penalty(text: str, rules: dict, event_matched: bool) -> int:
    penalty = 0
    for rule in rules["noise_patterns"]:
        if _word_pattern(rule["pattern"]).search(text):
            if rule.get("skip_if_event") and event_matched:
                continue
            penalty += rule["score"]  # 이미 음수
    return penalty


def _category_score(text: str, cat_keywords: dict, match_scores: dict) -> int:
    """한 카테고리에 대한 키워드 점수 계산."""
    strong = _count_matches(text, cat_keywords.get("strong", []))
    related = _count_matches(text, cat_keywords.get("related", []))
    raw = strong * match_scores["strong_keyword"] + related * match_scores["related_keyword"]
    return min(raw, match_scores["cap_per_category"])


def _assign_category(article: dict, rules: dict) -> tuple[str | None, int]:
    """가장 점수 높은 카테고리에 배정. (카테고리키, 키워드점수) 반환."""
    text = _haystack(article)
    match_scores = rules["match_scores"]
    best_cat = None
    best_score = 0
    for cat_key, cat_def in rules["categories"].items():
        score = _category_score(text, cat_def["keywords"], match_scores)
        if score > best_score:
            best_score = score
            best_cat = cat_key
    return best_cat, best_score


def score_articles(articles: list[dict], rules_path: str) -> dict:
    """카테고리별로 상위 기사를 추출. 반환 구조는 main JSON 형태."""
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f)

    # 카테고리별 후보 풀
    buckets: dict[str, list[dict]] = {k: [] for k in rules["categories"]}

    for art in articles:
        # URL 블랙리스트 — 영상/TV/팟캐스트 등 자동 제외
        if _is_blacklisted_url(art.get("link", "")):
            continue
        
        cat_key, kw_score = _assign_category(art, rules)
        if cat_key is None:
            continue

        text = _haystack(art)
        event_score, event_labels = _event_bonus_score(text, rules)
        noise_score = _noise_penalty(text, rules, event_matched=bool(event_labels))
        recency = _recency_score(art["published"], rules)
        source = art["source_weight"]

        total = kw_score + source + recency + event_score + noise_score

        if total < rules["min_score"]:
            continue

        scored = {
            **art,
            "category": cat_key,
            "category_display": rules["categories"][cat_key]["display_name"],
            "score": total,
            "score_breakdown": {
                "keyword": kw_score,
                "source": source,
                "recency": recency,
                "event_bonus": event_score,
                "noise_penalty": noise_score,
            },
            "event_labels": event_labels,
            # datetime은 JSON 직렬화 안 되니 ISO 문자열로
            "published": art["published"].isoformat(),
        }
        buckets[cat_key].append(scored)

    # 카테고리별 정렬 + 상위 N개 선정
    result_by_category = {}
    all_selected = []
    for cat_key, items in buckets.items():
        items.sort(key=lambda x: (-x["score"], x["published"]), reverse=False)
        # 위는 score 내림차순, published는 오름차순(최신우선이려면 -로 바꿀 수도)
        # 명확하게 다시 정렬:
        items.sort(key=lambda x: x["score"], reverse=True)
        target = rules["categories"][cat_key]["target_count"]
        selected = items[:target]
        result_by_category[cat_key] = {
            "display_name": rules["categories"][cat_key]["display_name"],
            "count": len(selected),
            "articles": selected,
        }
        all_selected.extend(selected)
        log.info(
            "Category %s: %d candidates → %d selected",
            cat_key, len(items), len(selected)
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": len(all_selected),
        "categories": result_by_category,
    }
