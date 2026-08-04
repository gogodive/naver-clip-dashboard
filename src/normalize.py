"""API 응답 → 저장 형태 변환. 순수 함수만 둔다(네트워크·파일 접근 없음)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def to_date(epoch_ms: int | None) -> str | None:
    """epoch 밀리초 → 'YYYY-MM-DD' (KST)."""
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, KST).strftime("%Y-%m-%d")


def _counted(node: dict | None) -> dict:
    """{count, diffRate, diffRateType} 노드를 평평하게 편다."""
    node = node or {}
    return {
        "count": node.get("count"),
        "diff_rate": node.get("diffRate"),
        "diff_type": node.get("diffRateType"),
    }


def summary(overview: dict, exposure: dict) -> dict:
    """주요 지표 요약 + 노출/클릭."""
    return {
        "play": _counted(overview.get("playCount")),
        "unique_user": _counted(overview.get("uniqueUser")),
        "like": _counted(overview.get("likeCount")),
        "follow_contribution": _counted(overview.get("subscriptionContribution")),
        "exposure": exposure.get("exposureCount"),
        "click": exposure.get("clickCount"),
        "click_rate": exposure.get("clickRate"),
    }


SERIES_KEYS = ("play", "new_user", "revisit_user", "follow_contribution", "follow")


def daily_series(playcount: dict, user: dict, contribution: dict,
                 follow: dict | None = None) -> list[dict]:
    """dataType 별 시계열 4종을 날짜 기준으로 합친다.

    API는 활동이 0인 날을 응답에서 통째로 뺀다. 그대로 그리면 x축 시간 간격이
    왜곡되므로 첫날~마지막날 사이의 빈 날짜를 0으로 채운다.
    """
    rows: dict[str, dict] = {}

    def put(series: list | None, key: str) -> None:
        for p in series or []:
            d = to_date(p.get("date"))
            if d is None:
                continue
            rows.setdefault(d, {"date": d})[key] = p.get("count")

    put(playcount.get("playCount"), "play")
    put(user.get("newUser"), "new_user")
    put(user.get("revisitingUser"), "revisit_user")
    put(contribution.get("contribution"), "follow_contribution")
    if follow:
        put(follow.get("dailyData"), "follow")

    if not rows:
        return []

    start = date.fromisoformat(min(rows))
    end = date.fromisoformat(max(rows))
    out = []
    for i in range((end - start).days + 1):
        d = (start + timedelta(days=i)).isoformat()
        row = rows.get(d, {"date": d})
        out.append({"date": d, **{k: row.get(k) or 0 for k in SERIES_KEYS}})
    return out


def entry_points(payload: dict) -> list[dict]:
    return [
        {"name": e.get("entryPoint"), "play": e.get("playCount"), "ratio": e.get("ratio")}
        for e in payload.get("entryPointPlayCounts") or []
    ]


def age_gender(payload: dict) -> list[dict]:
    node = payload.get("ageGenderRatioSet") or {}
    return [
        {"age": a.get("age"), "gender": a.get("gender"),
         "play": a.get("playCount"), "ratio": a.get("ratio")}
        for a in node.get("ageGenderRatios") or []
    ]


def clip_title(description: str | None) -> str:
    """description 첫 줄이 제목 역할을 한다."""
    if not description:
        return "(제목 없음)"
    first = description.strip().split("\n", 1)[0].strip()
    return first or "(제목 없음)"


def clip_record(item: dict) -> dict:
    """콘텐츠 목록 항목 → 저장 형태."""
    cat = item.get("category") or {}
    return {
        "no": item.get("mediaContentNo"),
        "video_id": item.get("videoId"),
        "title": clip_title(item.get("description")),
        "description": (item.get("description") or "")[:300],
        "thumbnail": item.get("thumbnail"),
        "posted_at": item.get("registerDateTime"),
        "duration": item.get("duration"),
        "play": item.get("playCount"),
        "like": item.get("likeCount"),
        "category": "/".join(x for x in (cat.get("firstCategory"),
                                         cat.get("secondCategory")) if x),
        "exposure_status": item.get("systemExposureStatusCode"),
        "deleted": False,
    }


def merge_clips(stored: list[dict], fresh: list[dict], now_iso: str) -> list[dict]:
    """현재 목록에 없는 과거 클립은 deleted 로 표시해 마지막 성과를 보존한다.

    클립 스튜디오는 삭제된 클립을 콘텐츠 목록에서 빼지만 계정 분석에는
    그 조회수가 그대로 남는다. 지운 클립의 성과를 잃지 않으려면 따로 붙들어야 한다.
    """
    fresh_by_no = {c["no"]: c for c in fresh}
    out: list[dict] = []

    for c in fresh:
        c["last_seen"] = now_iso
        out.append(c)

    for old in stored:
        if old.get("no") in fresh_by_no:
            continue
        gone = dict(old)
        gone["deleted"] = True
        out.append(gone)

    out.sort(key=lambda c: c.get("posted_at") or "", reverse=True)
    return out
