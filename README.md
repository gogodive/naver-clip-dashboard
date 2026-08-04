# 자사 네이버 클립 성과 대시보드

자사 네이버 클립 계정 3개의 성과를 매일 수집해 단일 HTML 대시보드로 만든다.

네이버 클립은 공개 API가 없다. 클립 크리에이터 스튜디오의 내부 JSON API를 쿠키 인증으로 호출한다.
API 구조는 `../docs/clip-studio-api.md` 참고 (리포지토리 밖에 둔다).

## 구조

```
src/session.py       저장된 쿠키 → 인증된 requests 세션
src/setup_login.py   최초 1회(또는 만료 시) 브라우저 로그인 — 쿠키 저장
src/clipapi.py       내부 API 클라이언트
src/normalize.py     API 응답 → 저장 형태 (순수 함수)
src/collect.py       계정별 수집 오케스트레이션
src/render.py        수집 결과 → HTML
src/template.html    대시보드 템플릿
src/notion_status.py 노션 허브 콜아웃 갱신
src/main.py          엔트리포인트
data/<네이버ID>.json  수집 결과 (커밋됨)
docs/index.html      생성된 대시보드 (커밋됨 — GitHub Pages 소스)
```

세션 쿠키는 **리포지토리 밖** `../profiles/<네이버ID>/` 에 저장한다. 이 리포는 공개다.

## 최초 설정

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

계정마다 한 번씩 로그인한다. 브라우저가 열리면 직접 로그인하면 된다.

```bash
.venv/bin/python -m src.setup_login funfun_seoki
```

노션 상태 기록을 쓰려면 `.env.example` 을 `.env` 로 복사해 `NOTION_TOKEN` 을 채운다.
노션 내부 통합을 만들고 허브 페이지에 **콘텐츠 업데이트** 권한으로 연결해야 한다.
없어도 수집·배포는 정상 동작한다.

GitHub Pages 는 **Settings → Pages → Deploy from a branch → main / docs** 로 설정한다.

## 실행

```bash
.venv/bin/python -m src.main
```

종료 코드 `2` 는 세션 만료를 뜻한다(수집·배포는 진행됨).

## 자동 실행

`run_daily.sh` 를 launchd 가 매일 05:00 에 실행한다. 맥이 꺼져 있으면 그날은 건너뛴다.

```bash
launchctl list | grep clip-dashboard        # 등록 확인
tail -f logs/launchd.out                    # 로그
```

## 세션이 만료되면

대시보드 상단과 노션 콜아웃에 🚨 경고가 뜬다. 해당 계정만 다시 로그인하면 된다.

```bash
.venv/bin/python -m src.setup_login <네이버ID>
```

클립 스튜디오는 `NID_AUT` 쿠키 만료보다 짧게 세션을 끊는다. 주기적인 재로그인이 필요하다.

## 테스트

```bash
.venv/bin/python -m pytest -q
```

네트워크를 타지 않는다. 순수 함수(`normalize`, `render`, `notion_status`)만 검증한다.

## 알아둘 것

- **데이터가 약 2일 지연된다.** "데이터 기준" 날짜가 오늘이 아닌 게 정상이다.
- **삭제된 클립의 조회수가 계정 전체 지표에는 남는다.** 그래서 전체 누적 조회수가
  현존 클립들의 합보다 클 수 있다. 삭제된 클립은 `deleted: true` 로 보존해 회색으로 표시한다.
- **계정마다 네이버 ID가 다르다.** 세션을 공유할 수 없어 계정별로 로그인해야 한다.
- 지표는 `period=all` 로 매번 전량을 다시 받는다. 하루 실패해도 데이터가 유실되지 않는다.
