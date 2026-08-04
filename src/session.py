"""네이버 세션 쿠키 로드 — 계정별 프로필 폴더의 스냅샷을 requests 세션에 주입한다.

클립 스튜디오 API는 Authorization 헤더 없이 naver.com 쿠키만으로 인증한다.
최초 1회 setup_login.py 로 브라우저 로그인해 두면 이후로는 브라우저가 필요 없다.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

COOKIE_FILE = "session_cookies.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


class SessionExpired(RuntimeError):
    """쿠키가 만료돼 재로그인이 필요하다."""

    def __init__(self, naver_id: str):
        self.naver_id = naver_id
        super().__init__(f"[{naver_id}] 네이버 세션 만료 — 재로그인이 필요합니다")


class MissingSession(RuntimeError):
    """아직 한 번도 로그인하지 않았다."""

    def __init__(self, naver_id: str):
        self.naver_id = naver_id
        super().__init__(f"[{naver_id}] 저장된 세션이 없습니다 — 최초 로그인이 필요합니다")


def cookie_path(profiles_dir: Path, naver_id: str) -> Path:
    return profiles_dir / naver_id / COOKIE_FILE


def build_session(profiles_dir: Path, naver_id: str) -> requests.Session:
    """저장된 쿠키로 인증된 세션을 만든다. 파일이 없으면 MissingSession."""
    path = cookie_path(profiles_dir, naver_id)
    if not path.exists():
        raise MissingSession(naver_id)

    cookies = json.loads(path.read_text())
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Referer": "https://clipcreators.naver.com/",
        "Accept": "application/json",
    })
    for c in cookies:
        if "naver.com" in c.get("domain", ""):
            s.cookies.set(c["name"], c["value"], domain=c["domain"], path=c.get("path", "/"))
    return s
