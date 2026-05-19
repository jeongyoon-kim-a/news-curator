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
from datetime import datetime, timezone
from typing import Iterable

import yaml

log = logging.getLogger(__name__)


def _haystack(article: dict) -> str:
    """매칭 대상 텍스트 (제목 + 요약)."""
    return f"{article['title']} {article.get('summary', '')}".lower()


def _count_matches(text: str, keywords: Iterable[str]) -> int:
    """텍스트에서 키워드가 매칭된 *키워드 개수* 반환 (출현 횟수 아님)."""
    matched = 0
    for kw in keywords:
        if kw.lower() in text:
            matched += 1
    return matched


def _has_any(text: str, keywords: Iterable[str]) -> bool:
    return any(kw.lower() in text for kw in keywords)


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
        if rule["pattern"].lower() in text:
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
