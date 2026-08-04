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


def collect_all(config: dict, profiles_dir: Path, data_dir: Path,
                now: datetime) -> list[dict]:
    """계정별로 수집. 실패한 계정은 직전 데이터를 그대로 유지한다."""
    data_dir.mkdir(parents=True, exist_ok=True)
    limit = config.get("clip_detail_limit", 60)
    out: list[dict] = []

    for account in config["accounts"]:
        naver_id = account["naver_id"]
        path = data_dir / f"{naver_id}.json"
        stored = json.loads(path.read_text()) if path.exists() else {}

        try:
            session = build_session(profiles_dir, naver_id)
            result = collect_account(ClipClient(session, naver_id), account,
                                     stored, now, limit)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            log.info("[%s] 수집 완료 — 클립 %d건", naver_id, len(result["clips"]))
        except (SessionExpired, MissingSession) as e:
            log.error("%s", e)
            result = stored or {"naver_id": naver_id, "name": account["name"], "clips": []}
            result["error"] = "session"
        except Exception:
            log.exception("[%s] 수집 실패", naver_id)
            result = stored or {"naver_id": naver_id, "name": account["name"], "clips": []}
            result["error"] = "fetch"

        out.append(result)

    return out
