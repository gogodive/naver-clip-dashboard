"""네이버 클립 크리에이터 스튜디오 내부 API 클라이언트.

공개 API가 아니다. 역설계 결과는 docs/clip-studio-api.md 참고.
지표 대부분은 period=all 로 전체 소급 조회가 되므로 매 실행마다 전량을 다시 받는다.
"""

from __future__ import annotations

import logging

import requests

from src.session import SessionExpired

log = logging.getLogger(__name__)

BASE = "https://clip-service-elb-public.io.naver.com"
TIMEOUT = 30
PAGE_SIZE = 100


class ClipAPIError(RuntimeError):
    def __init__(self, status: int, body: str):
        self.status = status
        super().__init__(f"클립 API 오류 {status}: {body[:200]}")


class ClipClient:
    def __init__(self, session: requests.Session, naver_id: str):
        self.s = session
        self.naver_id = naver_id

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        resp = self.s.get(f"{BASE}{path}", params=params, timeout=TIMEOUT,
                          allow_redirects=False)
        # 세션이 죽으면 401 이거나 로그인 페이지로 리다이렉트된다
        if resp.status_code in (401, 403):
            raise SessionExpired(self.naver_id)
        if resp.is_redirect and "nid.naver.com" in resp.headers.get("Location", ""):
            raise SessionExpired(self.naver_id)
        if resp.status_code != 200:
            raise ClipAPIError(resp.status_code, resp.text)
        return resp.json()

    # ---- 프로필 ----

    def get_profile(self) -> dict:
        """로그인한 계정의 프로필. self 는 배열을 반환하므로 첫 항목을 쓴다."""
        data = self._get("/studio/webapi/profiles/self")
        if not data:
            raise ClipAPIError(200, "profiles/self 가 빈 배열입니다")
        return data[0]

    # ---- 콘텐츠 목록 ----

    def get_clips(self, profile_key: str) -> list[dict]:
        """게시된 클립 전체. type=VOD 만 유효하다."""
        out: list[dict] = []
        page = 1
        while True:
            data = self._get(
                f"/studio/webapi/profiles/{profile_key}/contents",
                {"type": "VOD", "page": page, "size": PAGE_SIZE},
            )
            out.extend(data.get("items", []))
            total_pages = (data.get("commonInfo") or {}).get("totalPages") or 0
            if page >= total_pages:
                break
            page += 1
        return out

    # ---- 분석 ----

    def _analysis(self, profile_key: str, scope: str, endpoint: str,
                  params: dict | None = None) -> dict:
        """scope 는 'all' 또는 클립의 mediaContentNo."""
        return self._get(
            f"/studio/analysis/profiles/{profile_key}/media-contents/{scope}/{endpoint}",
            params,
        )

    def available_dates(self, profile_key: str, scope: str = "all") -> dict:
        return self._analysis(profile_key, scope, "available-dates")

    def overview(self, profile_key: str, scope: str = "all", **params) -> dict:
        return self._analysis(profile_key, scope, "overview", params)

    def exposure_click(self, profile_key: str, scope: str = "all", **params) -> dict:
        return self._analysis(profile_key, scope, "exposure-click", params)

    def entry_points(self, profile_key: str, scope: str = "all", **params) -> dict:
        return self._analysis(profile_key, scope, "entry-points", params)

    def age_gender(self, profile_key: str, scope: str = "all", **params) -> dict:
        return self._analysis(profile_key, scope, "age-gender", params)

    def detail(self, profile_key: str, data_type: str, scope: str = "all", **params) -> dict:
        return self._analysis(profile_key, scope, "detail", {"dataType": data_type, **params})

    def profile_detail(self, profile_key: str, data_type: str = "FOLLOW", **params) -> dict:
        """프로필 분석(팔로우 추이)은 media-contents 하위가 아니다."""
        return self._get(
            f"/studio/analysis/profiles/{profile_key}/detail",
            {"dataType": data_type, **params},
        )
