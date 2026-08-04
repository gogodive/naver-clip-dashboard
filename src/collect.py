"""계정별 수집 오케스트레이션.

period=all 로 전체를 소급 조회할 수 있으므로 매 실행마다 전량을 다시 받아 덮어쓴다.
인스타 프로젝트의 30일 동결·백필 병합이 여기서는 필요 없다.
유일한 예외가 삭제된 클립 보존(normalize.merge_clips).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import yaml

from src import normalize as nz
from src.clipapi import ClipClient
from src.naver_login import (LoginChallenge, LoginFailed, auto_login,
                             days_until_expiry, has_credentials, refresh_session)
from src.session import MissingSession, SessionExpired, build_session

log = logging.getLogger(__name__)


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _safe(fn, default):
    """개별 지표 호출 실패가 계정 전체를 죽이지 않게 한다.

    세션 만료는 계정 전체의 문제이므로 그대로 올려보낸다.
    """
    try:
        return fn()
    except SessionExpired:
        raise
    except Exception as e:
        log.warning("지표 조회 실패 (%s) — 건너뜀", type(e).__name__)
        return default


def _collect_clip_detail(client: ClipClient, pk: str, no: int) -> dict:
    """클립 1건의 유입처·연령성별·노출클릭 (전체 기간)."""
    scope = str(no)
    p = {"period": "all"}
    ov = _safe(lambda: client.overview(pk, scope, **p), {})
    ec = _safe(lambda: client.exposure_click(pk, scope, **p), {})
    return {
        "unique_user": ((ov.get("uniqueUser") or {}).get("count")),
        "exposure": ec.get("exposureCount"),
        "click": ec.get("clickCount"),
        "click_rate": ec.get("clickRate"),
        "entry_points": nz.entry_points(_safe(lambda: client.entry_points(pk, scope, **p), {})),
        "age_gender": nz.age_gender(_safe(lambda: client.age_gender(pk, scope, **p), {})),
    }


def collect_account(client: ClipClient, account: dict, stored: dict,
                    now: datetime, clip_detail_limit: int) -> dict:
    """계정 1개 수집. 실패는 호출자가 처리한다."""
    profile = client.get_profile()
    pk = profile["profileKey"]

    dates = _safe(lambda: client.available_dates(pk), {})
    data_through = (dates.get("toDate") or "")[:10] or None
    # 7d 는 증감률과 순시청자까지 함께 준다(custom 은 주지 않는다)
    win7 = {"period": "7d"}
    allp = {"period": "all"}

    clips = [nz.clip_record(i) for i in _safe(lambda: client.get_clips(pk), [])]
    now_iso = now.isoformat()

    # 상세 지표는 최근 클립부터 — 계정이 커져도 호출 수가 무한정 늘지 않게 막는다
    clips.sort(key=lambda c: c.get("posted_at") or "", reverse=True)
    for c in clips[:clip_detail_limit]:
        c.update(_collect_clip_detail(client, pk, c["no"]))
    if len(clips) > clip_detail_limit:
        log.info("클립 %d건 중 최근 %d건만 상세 수집", len(clips), clip_detail_limit)

    return {
        "naver_id": account["naver_id"],
        "name": account["name"],
        "clip_id": profile.get("clipId"),
        "profile_key": pk,
        "nickname": profile.get("nickname"),
        "followers": (profile.get("profileSummary") or {}).get("numberOfFollowers"),
        "registered_at": profile.get("registerDateTime"),
        "fetched_at": now_iso,
        "data_through": data_through,
        "data_from": (dates.get("fromDate") or "")[:10] or None,
        "totals": nz.summary(
            _safe(lambda: client.overview(pk, **allp), {}),
            _safe(lambda: client.exposure_click(pk, **allp), {}),
        ),
        "recent7": nz.summary(
            _safe(lambda: client.overview(pk, **win7), {}),
            _safe(lambda: client.exposure_click(pk, **win7), {}),
        ),
        "daily": nz.daily_series(
            _safe(lambda: client.detail(pk, "PLAYCOUNT", **allp), {}),
            _safe(lambda: client.detail(pk, "USER", **allp), {}),
            _safe(lambda: client.detail(pk, "CONTRIBUTION", **allp), {}),
            _safe(lambda: client.profile_detail(pk, "FOLLOW", **allp), {}),
        ),
        "entry_points": nz.entry_points(_safe(lambda: client.entry_points(pk, **allp), {})),
        "age_gender": nz.age_gender(_safe(lambda: client.age_gender(pk, **allp), {})),
        "clips": nz.merge_clips(stored.get("clips", []), clips, now_iso),
        "error": None,
    }


def should_relogin(days_left: float | None, threshold: float,
                   has_creds: bool) -> bool:
    """만료 전 선제 재로그인을 할지 판단한다.

    한 달에 한 번만 발동하는 분기라 틀려도 몇 주 뒤에나 드러난다 — 따로 떼어 검증한다.
    days_left 가 None 이면 아직 로그인한 적이 없다는 뜻이므로 여기서 손대지 않는다
    (수집을 시도해 보고 MissingSession 경로로 처리한다).
    """
    if days_left is None or not has_creds:
        return False
    return days_left <= threshold


def _collect_once(account: dict, profiles_dir: Path, stored: dict,
                  now: datetime, limit: int) -> dict:
    naver_id = account["naver_id"]
    session = build_session(profiles_dir, naver_id)
    return collect_account(ClipClient(session, naver_id), account, stored, now, limit)


def collect_all(config: dict, profiles_dir: Path, data_dir: Path,
                now: datetime) -> list[dict]:
    """계정별로 수집. 실패한 계정은 직전 데이터를 그대로 유지한다.

    세션 관리는 네 겹이다:
      0. 만료 임박(relogin_before_days 이내)이면 아직 멀쩡할 때 선제 재로그인
      1. 저장된 쿠키로 요청
      2. 401 이면 영구 프로필로 NID_SES 재발급 — 비밀번호 불필요
      3. 그래도 실패하면 키체인 비밀번호로 재로그인
    캡차·2차 인증이 뜨면 사람을 부른다(우회하지 않는다).
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    limit = config.get("clip_detail_limit", 60)
    login_cfg = config.get("login", {}) or {}
    headless = login_cfg.get("headless", True)
    relogin_before = login_cfg.get("relogin_before_days", 5)
    out: list[dict] = []

    for account in config["accounts"]:
        naver_id = account["naver_id"]
        path = data_dir / f"{naver_id}.json"
        stored = json.loads(path.read_text()) if path.exists() else {}

        def fallback(error: str) -> dict:
            r = stored or {"naver_id": naver_id, "name": account["name"], "clips": []}
            r["error"] = error
            return r

        # 만료가 코앞이면 아직 멀쩡할 때 미리 갈아 끼운다.
        # 만료 후에 대응하면 반드시 하루는 깨지고, 그날 캡차가 뜨면 복구할 여유도 없다.
        left = days_until_expiry(profiles_dir / naver_id)
        if should_relogin(left, relogin_before, has_credentials(naver_id)):
            log.info("[%s] 세션 만료까지 %.1f일 — 선제 재로그인", naver_id, left)
            try:
                auto_login(naver_id, profiles_dir / naver_id, headless=headless)
                left = days_until_expiry(profiles_dir / naver_id)
            except Exception as e:
                # 아직 남은 기간이 있으므로 수집은 계속한다
                log.warning("[%s] 선제 재로그인 실패(%s) — 남은 %.1f일 안에 수동 로그인 필요",
                            naver_id, type(e).__name__, left)

        try:
            try:
                result = _collect_once(account, profiles_dir, stored, now, limit)
            except (SessionExpired, MissingSession) as e:
                # 1단계: 비밀번호 없이 세션 재발급 시도 (NID_AUT 가 살아 있으면 성공)
                log.warning("%s — 세션 갱신 시도", e)
                try:
                    refresh_session(naver_id, profiles_dir / naver_id, headless=headless)
                except Exception as refresh_err:
                    # 2단계: 키체인 비밀번호로 재로그인
                    if not has_credentials(naver_id):
                        raise e from refresh_err
                    log.warning("[%s] 세션 갱신 실패 — 자동 재로그인 시도", naver_id)
                    auto_login(naver_id, profiles_dir / naver_id, headless=headless)
                result = _collect_once(account, profiles_dir, stored, now, limit)

            result["session_days_left"] = round(left, 1) if left is not None else None
            result["has_credentials"] = has_credentials(naver_id)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            log.info("[%s] 수집 완료 — 클립 %d건 (세션 잔여 %s일)", naver_id,
                     len(result["clips"]),
                     f"{left:.0f}" if left is not None else "?")
        except LoginChallenge as e:
            log.error("[%s] %s", naver_id, e)
            result = fallback("challenge")
        except (SessionExpired, MissingSession, LoginFailed) as e:
            log.error("%s", e)
            result = fallback("session")
        except Exception:
            log.exception("[%s] 수집 실패", naver_id)
            result = fallback("fetch")

        out.append(result)

    return out
