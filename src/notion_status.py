"""노션 허브 페이지 최상단 콜아웃에 마지막 실행 상태를 기록한다.

실패해도 수집·배포를 막지 않는다(부가 기능). 토큰이 없으면 조용히 건너뛴다.
세션 만료는 사람이 직접 재로그인해야 풀리므로 가장 눈에 띄게 알린다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TIMEOUT = 20
EXPIRY_WARN_DAYS = 5   # 세션 잔여가 이보다 적으면 선제 재로그인이 실패했다는 뜻


def build_status(accounts: list[dict], generated_at: datetime) -> tuple[str, str]:
    """(아이콘, 한 줄 상태 문장) 반환."""
    stamp = generated_at.astimezone(KST).strftime("%Y-%m-%d %H:%M")
    total = len(accounts)
    clips = sum(len(a.get("clips") or []) for a in accounts)

    challenged = [a["naver_id"] for a in accounts if a.get("error") == "challenge"]
    expired = [a["naver_id"] for a in accounts if a.get("error") == "session"]
    failed = [a["naver_id"] for a in accounts if a.get("error") == "fetch"]
    ok = total - len(challenged) - len(expired) - len(failed)

    # 캡차·2차 인증은 자동화로 못 넘는다 — 가장 먼저 알린다
    if challenged:
        names = ", ".join(challenged)
        return "🚨", (f"{stamp} · {ok}/{total}개 계정 갱신 — {names} 캡차/2차 인증 요구 "
                      f"(python -m src.setup_login {challenged[0]} 로 직접 로그인) "
                      f"· 해당 계정은 이전 데이터")
    if expired:
        names = ", ".join(expired)
        return "🚨", (f"{stamp} · {ok}/{total}개 계정 갱신 — {names} 자동 재로그인 실패 "
                      f"(python -m src.setup_login {expired[0]}) · 해당 계정은 이전 데이터")
    if failed:
        names = ", ".join(failed)
        return "⚠️", (f"{stamp} · {ok}/{total}개 계정 갱신 — 실패: {names} "
                      f"(해당 계정은 이전 데이터)")

    # 수집은 됐지만 재로그인 안전장치가 꺼져 있거나 실패했다.
    # 잔여 일수(쿠키 기한)는 원인이 아니라 증상이라 문구에 쓰지 않는다 — 매일 쓰는 한
    # 서버는 쿠키 기한이 지나도 세션을 받아준다(2026-10 실측). 원인을 말해야 사람이 움직인다.
    low = [a for a in accounts
           if a.get("session_days_left") is not None
           and a["session_days_left"] <= EXPIRY_WARN_DAYS]
    if low:
        head = f"{stamp} 갱신 완료 · {total}개 계정 · 클립 {clips:,}개"
        no_creds = [a["naver_id"] for a in low if not a.get("has_credentials")]
        if no_creds:
            return "⚠️", (f"{head} — 키체인 비어 있음({', '.join(no_creds)}): "
                          f"자동 재로그인·노션 갱신이 꺼질 수 있음 · ./setup_keychain.sh 실행")
        failed_login = [a["naver_id"] for a in low]
        return "⚠️", (f"{head} — 자동 재로그인 실패: {', '.join(failed_login)} · "
                      f"python -m src.setup_login {failed_login[0]}")

    return "✅", f"{stamp} 갱신 완료 · {total}개 계정 · 클립 {clips:,}개"


def update_callout(token: str, page_id: str, icon: str, text: str) -> bool:
    """페이지의 첫 콜아웃 블록을 갱신. 성공 시 True."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.get(f"{API}/blocks/{page_id}/children",
                            headers=headers, params={"page_size": 100}, timeout=TIMEOUT)
        if resp.status_code != 200:
            log.warning("노션 블록 조회 실패 (%s): %s", resp.status_code, resp.text[:200])
            return False
        block_id = next((b["id"] for b in resp.json().get("results", [])
                         if b.get("type") == "callout"), None)
        if not block_id:
            log.warning("노션 페이지에 콜아웃 블록이 없습니다 — 상태 기록 건너뜀")
            return False

        body = {"callout": {
            "rich_text": [{"type": "text", "text": {"content": text[:2000]}}],
            "icon": {"type": "emoji", "emoji": icon},
        }}
        resp = requests.patch(f"{API}/blocks/{block_id}", headers=headers,
                              json=body, timeout=TIMEOUT)
        if resp.status_code != 200:
            log.warning("노션 콜아웃 갱신 실패 (%s): %s", resp.status_code, resp.text[:200])
            return False
        return True
    except requests.RequestException:
        log.exception("노션 상태 기록 중 네트워크 오류")
        return False
