"""
엔트리 포인트
=============
GitHub Actions가 이 스크립트를 실행한다.
사용법: python scripts/run.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# 같은 폴더의 모듈 import 가능하게
sys.path.insert(0, str(Path(__file__).parent))

from collect import collect_all  # noqa: E402
from score import score_articles  # noqa: E402


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    setup_logging()
    log = logging.getLogger("run")

    repo_root = Path(__file__).resolve().parent.parent
    sources_path = repo_root / "config" / "sources.yaml"
    rules_path = repo_root / "config" / "rules.yaml"
    output_path = repo_root / "data" / "daily.json"

    log.info("=== News Curator: starting ===")
    log.info("Sources: %s", sources_path)
    log.info("Rules:   %s", rules_path)
    log.info("Output:  %s", output_path)

    # 1. 수집
    articles = collect_all(str(sources_path))
    if not articles:
        log.error("No articles collected. Aborting without overwriting daily.json.")
        return 1

    # 2. 스코어링 + 카테고리 분류
    result = score_articles(articles, str(rules_path))

    # 3. JSON 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log.info("=== Done. Total selected: %d ===", result["total_articles"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
