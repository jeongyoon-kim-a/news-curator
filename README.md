# News Curator

매일 새벽 6시(KST) 빅테크/일론 머스크/디지털 자산/핀테크/미래에셋 관련 뉴스를
국내외 매체에서 수집하고 룰 기반으로 중요도를 매겨 `data/daily.json`에 저장합니다.

이 JSON을 News Multi-Search 사이트가 fetch해서 "오늘의 큐레이션" 섹션에 표시합니다.

## 구조

```
news-curator/
├── .github/workflows/daily.yml   # 매일 06:00 KST 자동 실행
├── scripts/
│   ├── collect.py                # RSS/검색 수집
│   ├── score.py                  # 룰 기반 스코어링
│   └── run.py                    # collect → score → JSON 출력 entry point
├── config/
│   ├── sources.yaml              # 매체별 RSS URL, 가중치
│   └── rules.yaml                # 키워드, 카테고리, 점수 가중치 (튜닝 핵심)
└── data/
    └── daily.json                # 매일 갱신되는 결과
```

## 셋업 (1회만)

1. 이 폴더를 GitHub repo로 push (private/public 무관, public이면 무료 Actions 한도 넉넉)
2. Settings → Actions → General → Workflow permissions → "Read and write permissions" 체크
   (Actions가 data/daily.json을 commit해야 하므로)
3. Settings → Pages → Source를 `main` branch로 설정하면 `https://<user>.github.io/news-curator/data/daily.json`에서 JSON을 직접 fetch 가능

## 일상 운영

- 매일 아침 사이트에서 결과 확인
- "이건 왜 빠졌지" / "이건 왜 올라왔지" 싶으면 `config/rules.yaml` 가중치 수정 후 commit
- 첫 1~2주는 튜닝 기간이라 생각하기
