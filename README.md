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

노션 상태 기록을 쓰려면 내부 통합 토큰이 필요하다. 없어도 수집·배포는 정상 동작한다.

1. https://www.notion.so/my-integrations 에서 내부 통합을 만들거나 기존 것의 시크릿을 복사
2. 허브 페이지 우측 상단 `⋯` → **연결** → 그 통합을 추가 (콘텐츠 업데이트 권한 필요)
3. 키체인에 저장

```bash
security add-generic-password -s naver-clip -a notion-token -w
```

토큰은 키체인을 먼저 보고, 없으면 환경변수 `NOTION_TOKEN` 을 쓴다.

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

## 세션 관리

네이버 세션에는 두 개의 쿠키가 필요하다.

| 쿠키 | 수명 | 성질 |
|---|---|---|
| `NID_AUT` | **약 30일 고정** | '로그인 상태 유지'를 켜야 영구 쿠키로 발급된다 |
| `NID_SES` | 브라우저 종료 시 소멸 | `NID_AUT` 가 살아 있으면 재방문 시 자동 재발급 |

**`NID_AUT` 만료는 사용해도 연장되지 않는다.** 실측으로 확인했다 — 19일 동안 매일 써도
만료일이 로그인 당일 기준 그대로였다. 그래서 30일마다 반드시 새로 로그인해야 한다.

이걸 사람 손 없이 넘기려고 수집기는 네 겹으로 방어한다.

| 단계 | 동작 | 비밀번호 |
|---|---|---|
| 0 | 만료 `relogin_before_days`(기본 5일) 이내면 **미리** 재로그인 | 키체인 |
| 1 | 저장된 쿠키로 요청 (평상시) | 불필요 |
| 2 | 401 이면 영구 프로필로 `NID_SES` 재발급 | 불필요 |
| 3 | 그래도 실패하면 재로그인 | 키체인 |

0단계가 핵심이다. 만료된 뒤에 대응하면 반드시 하루는 깨지고, 하필 그날 캡차가 뜨면
복구할 여유도 없다. 아직 5일 남았을 때 갈아 끼우면 실패해도 다시 시도할 날이 남는다.

### 비밀번호 저장

키체인에만 둔다. 리포지토리·설정파일·환경변수 어디에도 저장하지 않는다.

```bash
security add-generic-password -s naver-clip -a <네이버ID> -w
```

비밀번호를 대화형으로 입력받으므로 셸 히스토리에도 남지 않는다. 저장 후 확인:

```bash
.venv/bin/python -m src.setup_login <네이버ID> --auto
```

비밀번호가 없으면 0·3단계를 건너뛰고 1·2단계만 동작한다. 그 경우 30일마다 수동 로그인이 필요하다.

### 캡차·2차 인증

자동화로 넘지 않는다. 뜨는 즉시 중단하고 대시보드·노션에 🚨 와 계정명을 띄운다.
나머지 계정은 정상 수집된다. 직접 로그인하면 된다.

```bash
.venv/bin/python -m src.setup_login <네이버ID>
```

'로그인 상태 유지'가 자동으로 켜지고, 켜지지 않았으면 종료 코드 `1` 과 함께 경고한다.

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
