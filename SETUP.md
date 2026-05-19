# 셋업 가이드

처음부터 끝까지 따라하면 매일 새벽 6시에 자동으로 큐레이션된 뉴스를 사이트에서 볼 수 있습니다.

---

## 1단계: GitHub Repo 생성 및 파일 업로드

1. GitHub에서 새 repo 생성. 이름은 `news-curator` 추천 (public 권장 — Actions 무료 한도 넉넉)
2. 로컬에서:

```bash
cd news-curator
git init
git add .
git commit -m "Initial setup"
git remote add origin https://github.com/<YOUR-USERNAME>/news-curator.git
git branch -M main
git push -u origin main
```

---

## 2단계: GitHub Actions 권한 설정 (필수)

Actions가 `data/daily.json`을 자동 commit해야 하므로:

1. Repo → **Settings** → **Actions** → **General**
2. 아래로 스크롤해서 **Workflow permissions** 섹션
3. **"Read and write permissions"** 선택 → **Save**

이거 안 하면 Actions가 돌긴 하는데 push 단계에서 실패합니다.

---

## 3단계: GitHub Pages 활성화

JSON을 사이트에서 읽으려면 Pages 호스팅이 필요해요:

1. Repo → **Settings** → **Pages**
2. **Source**: "Deploy from a branch" 선택
3. **Branch**: `main` / `/ (root)` 선택 → **Save**
4. 1~2분 후 `https://<YOUR-USERNAME>.github.io/news-curator/` 가 활성화됨

이러면 `data/daily.json`은 다음 URL에서 접근 가능:
```
https://<YOUR-USERNAME>.github.io/news-curator/data/daily.json
```

---

## 4단계: 첫 실행 (수동)

스케줄을 기다리지 않고 바로 테스트:

1. Repo → **Actions** 탭 클릭
2. 좌측에서 **"Daily News Curation"** workflow 선택
3. 우측 **"Run workflow"** 버튼 → **Run workflow**
4. 1~2분 후 완료. 초록색 체크 뜨면 성공.
5. Repo 메인에서 `data/daily.json` 클릭해서 결과 확인

---

## 5단계: News Multi-Search 사이트에 섹션 추가

기존 사이트 repo에서 `index.html` 열어서:

1. `site-snippet.html` 파일의 내용을 복사
2. 기존 `<section>` (예: 국내/국제 검색 박스) **위 또는 아래**에 붙여넣기
3. 스크립트 안의 `DATA_URL` 한 줄 수정:
   ```javascript
   const DATA_URL = "https://<YOUR-GITHUB-USERNAME>.github.io/news-curator/data/daily.json";
   ```
4. commit + push → 사이트 갱신되면 끝

---

## 일상 운영: 룰 튜닝 (가장 중요)

처음 1~2주는 매일 아침 결과 보고 `config/rules.yaml` 손보는 시기예요.

### "이 기사가 빠졌어야 했는데 올라왔음" → 노이즈 추가

`noise_patterns`에 패턴 추가:
```yaml
- pattern: "오전 시황"
  score: -3
```

### "이 기사가 올라왔어야 했는데 빠짐" → 키워드 보강

해당 카테고리의 `keywords.strong` 또는 `related`에 추가.
또는 카테고리 매칭은 됐는데 점수가 낮아서 탈락한 경우 → 어떤 매체였는지 보고 `sources.yaml`에서 `weight` 올림.

### "이 매체에서 너무 많이 올라옴"

`sources.yaml`에서 해당 매체의 `weight` 1단계 낮춤.

### "특정 분야 너무 적게/많이 올라옴"

`rules.yaml`의 카테고리 `target_count` 조정.

---

## 트러블슈팅

### Actions가 실패함 (push 권한 에러)
2단계 권한 설정 다시 확인.

### data/daily.json은 만들어졌는데 사이트에서 안 보임
- Pages가 활성화됐는지 확인
- 브라우저 콘솔에서 fetch 에러 메시지 확인
- DATA_URL 오타 점검 (특히 username 부분)
- CORS 에러면 같은 도메인에서 호스팅하는 게 가장 단순함 (옵션 A 참고)

### 첫 실행에 기사가 너무 적게 잡힘
- `min_score`를 낮춰보기 (기본 5 → 3 정도)
- 키워드 매칭이 약한 카테고리의 키워드 보강
- Actions 로그에서 "Total raw articles" 숫자 확인 — 너무 적으면 RSS 자체가 문제

### Bloomberg/Information이 안 잡힘
- Bloomberg는 RSS 제공하지만 가끔 막힘 → Google News fallback으로 type을 `gnews`로 바꿔보기
- The Information은 무료 RSS 없어서 Google News로만 가져옴 (지연/누락 가능)

---

## 데이터 백업

매일 commit이 쌓이므로 git history가 자동 백업 역할을 합니다.
과거 어느 날 자료가 보고 싶으면:
```bash
git log --all -- data/daily.json
git show <commit>:data/daily.json
```

원하시면 별도로 `data/archive/YYYY-MM-DD.json`에 보관하도록 workflow 수정 가능.
