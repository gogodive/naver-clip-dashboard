"""수집 결과 → 단일 HTML 대시보드."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Undefined, select_autoescape

KST = timezone(timedelta(hours=9))
_TEMPLATE_DIR = Path(__file__).parent

HOT_RATIO = 2.0          # 계정 중앙값 대비 이 배수 이상이면 🔥
HOT_RATIO_LABELED = 3.0  # 이 배수 이상이면 배수까지 표기 (🔥 4.2x)
HOT_MIN_CLIPS = 5        # 조회수 있는 클립이 이보다 적으면 표시 안 함
ENTRY_TOP = 6            # 유입처는 상위 N개만 표시하고 나머지는 합산
EXPIRY_WARN_DAYS = 5     # 세션 잔여가 이보다 적으면 배너로 알린다

AGE_LABELS = {
    "AGE_10": "10대", "AGE_20": "20대", "AGE_30": "30대",
    "AGE_40": "40대", "AGE_50": "50대", "AGE_60_UP": "60대+",
}
AGE_ORDER = list(AGE_LABELS)


def _fmt_num(v) -> str:
    if v is None or isinstance(v, Undefined):
        return "–"
    return f"{v:,}"


def _fmt_date(ts: str | None) -> str:
    if not ts:
        return ""
    return ts[:10]


def _days_since(posted_at: str | None, generated_at: datetime) -> int | None:
    if not posted_at:
        return None
    try:
        dt = datetime.fromisoformat(posted_at)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return (generated_at - dt).days


def _annotate_hot(clips: list[dict]) -> None:
    """계정 내 조회수 중앙값 대비 배수로 히트 클립에 _hot 라벨을 단다.

    계정 간 절대 비교는 무의미하므로 항상 계정 내부 기준으로만 판정한다.
    """
    live = [c for c in clips if not c.get("deleted")]
    views = [c.get("play") for c in live]
    views = [v for v in views if isinstance(v, int) and v > 0]
    if len(views) < HOT_MIN_CLIPS:
        return
    median = statistics.median(views)
    if median <= 0:
        return
    for c in live:
        v = c.get("play")
        if isinstance(v, int) and v / median >= HOT_RATIO:
            ratio = v / median
            c["_hot"] = f"🔥 {ratio:.1f}x" if ratio >= HOT_RATIO_LABELED else "🔥"


def _entry_rows(entry_points: list[dict]) -> list[dict]:
    """상위 N개 + 나머지 합산. ratio 는 API 값을 그대로 쓴다."""
    rows = [e for e in entry_points if (e.get("play") or 0) > 0]
    rows.sort(key=lambda e: e.get("play") or 0, reverse=True)
    top = rows[:ENTRY_TOP]
    rest = rows[ENTRY_TOP:]
    if rest:
        top.append({
            "name": f"그 외 {len(rest)}종",
            "play": sum(e.get("play") or 0 for e in rest),
            "ratio": round(sum(e.get("ratio") or 0 for e in rest), 1),
        })
    return top


def _age_rows(age_gender: list[dict]) -> list[dict]:
    """연령대별 남/여 비율. 최대값 대비 막대 너비를 미리 계산한다."""
    by_age = {a: {"age": AGE_LABELS[a], "male": 0, "female": 0} for a in AGE_ORDER}
    for r in age_gender:
        node = by_age.get(r.get("age"))
        if node is None:
            continue
        key = "male" if r.get("gender") == "MALE" else "female"
        node[key] = r.get("ratio") or 0
    rows = [v for v in by_age.values() if v["male"] or v["female"]]
    peak = max((max(r["male"], r["female"]) for r in rows), default=0)
    for r in rows:
        r["male_w"] = round(r["male"] / peak * 100, 1) if peak else 0
        r["female_w"] = round(r["female"] / peak * 100, 1) if peak else 0
    return rows


def _gender_split(age_gender: list[dict]) -> dict:
    male = sum(r.get("play") or 0 for r in age_gender if r.get("gender") == "MALE")
    female = sum(r.get("play") or 0 for r in age_gender if r.get("gender") == "FEMALE")
    total = male + female
    if not total:
        return {"male": 0, "female": 0}
    return {"male": round(male / total * 100), "female": round(female / total * 100)}


def _chart_payload(daily: list[dict]) -> dict | None:
    """추이 차트용 {labels, play, viewer}. 조회 활동이 없으면 None.

    클립이 0건이어도 팔로워 추이 때문에 시계열 자체는 존재한다.
    그 경우 0만 늘어선 차트가 되므로 그리지 않는다.
    """
    rows = [d for d in daily if d.get("play") is not None]
    if len(rows) < 2:
        return None
    play = [d.get("play") or 0 for d in rows]
    viewer = [(d.get("new_user") or 0) + (d.get("revisit_user") or 0) for d in rows]
    if not any(play) and not any(viewer):
        return None
    return {"labels": [d["date"] for d in rows], "play": play, "viewer": viewer}


def render_html(accounts: list[dict], generated_at: datetime) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["num"] = _fmt_num
    env.filters["date"] = _fmt_date
    tpl = env.get_template("template.html")

    charts: dict[int, dict] = {}
    for i, acc in enumerate(accounts):
        clips = acc.get("clips") or []
        for c in clips:
            c["_days"] = _days_since(c.get("posted_at"), generated_at)
        _annotate_hot(clips)
        acc["_live_clips"] = sum(1 for c in clips if not c.get("deleted"))
        acc["_deleted_clips"] = sum(1 for c in clips if c.get("deleted"))
        left = acc.get("session_days_left")
        acc["_expiring"] = left if isinstance(left, (int, float)) and left <= EXPIRY_WARN_DAYS else None
        acc["_entry_rows"] = _entry_rows(acc.get("entry_points") or [])
        acc["_age_rows"] = _age_rows(acc.get("age_gender") or [])
        acc["_gender"] = _gender_split(acc.get("age_gender") or [])
        payload = _chart_payload(acc.get("daily") or [])
        acc["_has_chart"] = payload is not None
        if payload:
            charts[i] = payload

    # "<" 를 이스케이프해 제목의 </script> 로 스크립트가 닫히는 것을 방지
    chart_json = json.dumps(charts, ensure_ascii=False).replace("<", "\\u003c")
    return tpl.render(
        accounts=accounts,
        chart_json=chart_json,
        generated_label=generated_at.astimezone(KST).strftime("%Y-%m-%d %H:%M"),
    )
