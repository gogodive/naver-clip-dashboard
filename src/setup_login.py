"""최초 1회(또는 세션 만료 시) 수동 로그인 — 계정 쿠키를 저장한다.

사용법: .venv/bin/python -m src.setup_login <네이버ID>
브라우저가 열리면 직접 로그인하세요. 비밀번호는 이 스크립트가 다루지 않습니다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent
LOGIN_URL = "https://nid.naver.com/nidlogin.login"
STUDIO_URL = "https://clipcreators.naver.com/web/dashboard"
WAIT_MINUTES = 10


def main() -> int:
    if len(sys.argv) < 2:
        print("사용법: python -m src.setup_login <네이버ID>", file=sys.stderr)
        return 1
    naver_id = sys.argv[1]

    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    known = {a["naver_id"] for a in config["accounts"]}
    if naver_id not in known:
        print(f"config.yaml 에 없는 계정입니다: {naver_id} (등록된 계정: {', '.join(sorted(known))})",
              file=sys.stderr)
        return 1

    profile_dir = (ROOT / config["profiles_dir"] / naver_id).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1400, "height": 950},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LOGIN_URL)
        page.wait_for_timeout(2000)

        # '로그인 상태 유지'를 켜 두면 쿠키 수명이 길어진다
        for css in ("#keep", "input[name='nvlong']", "#nvlong", ".keep_check input"):
            try:
                page.locator(css).first.check(timeout=1500)
                break
            except Exception:
                continue

        print(f"\n>>> [{naver_id}] 브라우저에서 로그인해 주세요 (최대 {WAIT_MINUTES}분 대기)\n",
              flush=True)

        deadline = time.time() + WAIT_MINUTES * 60
        while time.time() < deadline:
            time.sleep(3)
            try:
                names = {c["name"] for c in ctx.cookies("https://naver.com")}
            except Exception:
                print("브라우저가 닫혔습니다.", file=sys.stderr)
                return 1
            if {"NID_AUT", "NID_SES"} <= names:
                break
        else:
            print("시간 초과 — 로그인이 확인되지 않았습니다.", file=sys.stderr)
            ctx.close()
            return 1

        # 스튜디오를 한 번 열어 서비스 쿠키까지 받아 둔다
        try:
            page.goto(STUDIO_URL, wait_until="networkidle", timeout=45000)
            page.wait_for_timeout(3000)
        except Exception:
            pass

        cookies = [c for c in ctx.cookies() if "naver.com" in c.get("domain", "")]
        (profile_dir / "session_cookies.json").write_text(
            json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
        print(f"로그인 성공 — 쿠키 {len(cookies)}개 저장: {profile_dir}", flush=True)
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
