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
