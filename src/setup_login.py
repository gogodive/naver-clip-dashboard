"""네이버 로그인 — 수동(브라우저 직접 입력) 또는 자동(키체인 비밀번호).

    python -m src.setup_login <네이버ID>          수동: 브라우저가 열리면 직접 로그인
    python -m src.setup_login <네이버ID> --auto   자동: 키체인 비밀번호로 로그인 (검증용)

수동 로그인 시 '로그인 상태 유지'는 자동으로 켜진다. 이게 꺼져 있으면 NID_AUT 가
세션 쿠키로 발급돼 브라우저를 닫는 순간 죽는다.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

from src.naver_login import (LOGIN_URL, STUDIO_URL, LoginChallenge, LoginFailed,
                             NoCredentials, auto_login, ensure_stay_checked,
                             save_cookies)

ROOT = Path(__file__).parent.parent
WAIT_MINUTES = 10


def _profile_dir(naver_id: str) -> Path:
    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    known = {a["naver_id"] for a in config["accounts"]}
    if naver_id not in known:
        raise SystemExit(f"config.yaml 에 없는 계정입니다: {naver_id} "
                         f"(등록된 계정: {', '.join(sorted(known))})")
    return (ROOT / config["profiles_dir"] / naver_id).resolve()


def manual_login(naver_id: str, profile_dir: Path) -> int:
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1400, "height": 950},
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)

            if ensure_stay_checked(page):
                print("'로그인 상태 유지' 자동 체크 완료", flush=True)
            else:
                print("!! '로그인 상태 유지'를 자동으로 켜지 못했습니다 — "
                      "화면에서 직접 켜고 로그인하세요. 안 켜면 세션이 하루도 못 갑니다.",
                      file=sys.stderr, flush=True)

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
                return 1

            try:
                page.goto(STUDIO_URL, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2500)
            except Exception:
                pass

            cookies = save_cookies(ctx, profile_dir)
            auth = next((c for c in cookies if c["name"] == "NID_AUT"), None)
            persistent = bool(auth and auth.get("expires", -1) > 0)
            print(f"로그인 성공 — 쿠키 {len(cookies)}개 저장: {profile_dir}", flush=True)
            print("세션 지속성: " + ("장기 유지됨 ✓" if persistent else
                                  "!! 브라우저 종료 시 만료 — '로그인 상태 유지'를 켜고 다시 시도하세요"),
                  flush=True)
            return 0 if persistent else 1
        finally:
            ctx.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__, file=sys.stderr)
        return 1
    naver_id = args[0]
    profile_dir = _profile_dir(naver_id)

    if "--auto" in sys.argv:
        try:
            auto_login(naver_id, profile_dir, headless="--headed" not in sys.argv)
            return 0
        except NoCredentials as e:
            print(e, file=sys.stderr)
            return 1
        except LoginChallenge as e:
            print(f"[{naver_id}] {e}\n→ python -m src.setup_login {naver_id} 로 직접 로그인하세요.",
                  file=sys.stderr)
            return 3
        except LoginFailed as e:
            print(f"[{naver_id}] 자동 로그인 실패: {e}", file=sys.stderr)
            return 1

    return manual_login(naver_id, profile_dir)


if __name__ == "__main__":
    sys.exit(main())
