"""네이버 로그인 — 수동/자동 공용.

비밀번호는 이 리포지토리 어디에도 저장하지 않는다. macOS 키체인에서만 읽는다.
저장은 사용자가 직접 한다(대화형으로 입력받으므로 값이 셸 히스토리에도 남지 않는다):

    security add-generic-password -s naver-clip -a <네이버ID> -w

캡차나 2차 인증이 뜨면 자동화는 중단한다. 우회하지 않는다 — 사람이 직접 로그인해야 한다.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)

LOGIN_URL = "https://nid.naver.com/nidlogin.login"
STUDIO_URL = "https://clipcreators.naver.com/web/dashboard"
KEYCHAIN_SERVICE = "naver-clip"

SEL_ID = "#id"
SEL_PW = "#pw"
SEL_STAY = "#loginStay"                       # name=nvlong — 이게 켜져야 NID_AUT 가 30일짜리가 된다
SEL_SUBMIT = "#loginBtn_column, #loginBtn_row"


class LoginChallenge(RuntimeError):
    """캡차·2차 인증 등 사람이 직접 처리해야 하는 관문."""


class LoginFailed(RuntimeError):
    """아이디/비밀번호가 틀렸거나 알 수 없는 이유로 실패."""


class NoCredentials(RuntimeError):
    def __init__(self, naver_id: str):
        self.naver_id = naver_id
        super().__init__(
            f"[{naver_id}] 키체인에 비밀번호가 없습니다. 먼저 저장하세요:\n"
            f"  security add-generic-password -s {KEYCHAIN_SERVICE} -a {naver_id} -w"
        )


def read_password(naver_id: str) -> str:
    """macOS 키체인에서 비밀번호를 읽는다. 로그에 절대 남기지 않는다."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", naver_id, "-w"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise NoCredentials(naver_id) from e
    if r.returncode != 0 or not r.stdout.strip():
        raise NoCredentials(naver_id)
    return r.stdout.rstrip("\n")


def has_credentials(naver_id: str) -> bool:
    try:
        read_password(naver_id)
        return True
    except NoCredentials:
        return False


def _ensure_stay_checked(page) -> None:
    """'로그인 상태 유지'를 켠다.

    이게 꺼져 있으면 NID_AUT 가 세션 쿠키로 발급돼 브라우저를 닫는 순간 죽는다.
    조용히 실패하면 매일 재로그인하게 되므로 확인까지 한다.
    """
    page.locator(SEL_STAY).check(timeout=5000)
    if not page.locator(SEL_STAY).is_checked():
        raise LoginFailed("'로그인 상태 유지'를 켜지 못했습니다 — 세션이 하루도 못 갑니다")


def _classify_landing(page) -> None:
    """로그인 시도 후 화면을 보고 실패 원인을 분류한다."""
    url = page.url
    if "captcha" in url.lower() or page.locator("#ncaptcha, .captcha").count():
        raise LoginChallenge("캡차가 요구됐습니다 — 사람이 직접 로그인해야 합니다")
    if any(k in url for k in ("deviceConfirm", "otp", "twoFactor", "need2", "authTypeSelect")):
        raise LoginChallenge("2차 인증이 요구됐습니다 — 사람이 직접 로그인해야 합니다")
    if "nidlogin" in url:
        err = ""
        try:
            err = page.locator(".error_message, #err_common").first.inner_text(timeout=1500)
        except Exception:
            pass
        raise LoginFailed(f"로그인 화면에 머물러 있습니다 — {err or '아이디/비밀번호 확인 필요'}")


def _wait_logged_in(ctx, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        names = {c["name"] for c in ctx.cookies("https://naver.com")}
        if {"NID_AUT", "NID_SES"} <= names:
            return True
        time.sleep(1.5)
    return False


def save_cookies(ctx, profile_dir: Path) -> list[dict]:
    """naver.com 쿠키를 스냅샷으로 저장하고, 지속성 여부를 경고한다."""
    cookies = [c for c in ctx.cookies() if "naver.com" in c.get("domain", "")]
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "session_cookies.json").write_text(
        json.dumps(cookies, ensure_ascii=False), encoding="utf-8")

    auth = next((c for c in cookies if c["name"] == "NID_AUT"), None)
    if not auth or auth.get("expires", -1) <= 0:
        log.warning("NID_AUT 가 세션 쿠키입니다 — '로그인 상태 유지'가 꺼진 상태로 로그인됐습니다")
    return cookies


def refresh_session(naver_id: str, profile_dir: Path, headless: bool = True) -> list[dict]:
    """비밀번호 없이 세션을 되살린다.

    NID_SES 는 세션 쿠키라 브라우저를 닫으면 사라진다. 하지만 '로그인 상태 유지'로
    받은 NID_AUT 가 영구 프로필에 남아 있으면, 스튜디오를 한 번 여는 것만으로
    네이버가 NID_SES 를 재발급해 준다. 그게 안 되면 SessionExpired 를 던진다.

    비밀번호가 필요 없으므로 자동 재로그인보다 먼저 시도한다.
    """
    from playwright.sync_api import sync_playwright

    from src.session import SessionExpired

    if not profile_dir.exists():
        raise SessionExpired(naver_id)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1400, "height": 950},
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            if "nid.naver.com" in page.url:
                raise SessionExpired(naver_id)
            cookies = save_cookies(ctx, profile_dir)
            log.info("[%s] 세션 갱신 성공 (비밀번호 불필요) — 쿠키 %d개", naver_id, len(cookies))
            return cookies
        finally:
            ctx.close()


def auto_login(naver_id: str, profile_dir: Path, headless: bool = True) -> list[dict]:
    """키체인 비밀번호로 로그인해 쿠키를 저장한다. 저장된 쿠키 목록 반환.

    캡차·2차 인증이 뜨면 LoginChallenge 를 던진다(우회하지 않는다).
    """
    from playwright.sync_api import sync_playwright

    password = read_password(naver_id)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1400, "height": 950},
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)

            _ensure_stay_checked(page)
            # 사람이 치는 속도로 입력한다. 한 번에 밀어 넣으면 네이버가 반려하는 경우가 있다.
            page.locator(SEL_ID).click()
            page.locator(SEL_ID).type(naver_id, delay=60)
            page.locator(SEL_PW).click()
            page.locator(SEL_PW).type(password, delay=60)
            del password
            page.locator(SEL_SUBMIT).first.click()

            page.wait_for_timeout(4000)
            if not _wait_logged_in(ctx, timeout_s=20):
                _classify_landing(page)
                raise LoginFailed("로그인 결과를 확인하지 못했습니다")

            # 스튜디오를 한 번 열어 서비스 쿠키까지 받아 둔다
            try:
                page.goto(STUDIO_URL, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2500)
            except Exception:
                pass

            cookies = save_cookies(ctx, profile_dir)
            log.info("[%s] 자동 로그인 성공 — 쿠키 %d개 저장", naver_id, len(cookies))
            return cookies
        finally:
            ctx.close()
