from datetime import datetime, timedelta, timezone

from src import render

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 8, 5, 5, 0, tzinfo=KST)


def clips(*plays):
    return [{"no": i, "play": p, "deleted": False} for i, p in enumerate(plays)]


def test_annotate_hot_needs_minimum_sample():
    cs = clips(100, 100, 100, 1000)          # 4건 — 기준 미달
    render._annotate_hot(cs)
    assert all("_hot" not in c for c in cs)


def test_annotate_hot_marks_two_x_median():
    cs = clips(100, 100, 100, 100, 250)      # 중앙값 100 → 250은 2.5배
    render._annotate_hot(cs)
    assert cs[4]["_hot"] == "🔥"
    assert all("_hot" not in c for c in cs[:4])


def test_annotate_hot_labels_ratio_at_three_x():
    cs = clips(100, 100, 100, 100, 420)      # 4.2배
    render._annotate_hot(cs)
    assert cs[4]["_hot"] == "🔥 4.2x"


def test_annotate_hot_ignores_deleted_clips():
    """삭제된 클립이 중앙값을 흔들면 살아있는 클립 판정이 왜곡된다."""
    cs = clips(100, 100, 100, 100, 250)
    cs.append({"no": 9, "play": 99999, "deleted": True})
    render._annotate_hot(cs)
    assert cs[4]["_hot"] == "🔥"
    assert "_hot" not in cs[5]


def test_entry_rows_collapses_tail():
    rows = render._entry_rows([
        {"name": f"경로{i}", "play": 100 - i, "ratio": 10.0} for i in range(9)
    ])
    assert len(rows) == render.ENTRY_TOP + 1
    assert rows[-1]["name"] == "그 외 3종"
    assert rows[-1]["ratio"] == 30.0


def test_entry_rows_drops_zero_play():
    rows = render._entry_rows([{"name": "a", "play": 0, "ratio": 0},
                               {"name": "b", "play": 5, "ratio": 100}])
    assert [r["name"] for r in rows] == ["b"]


def test_age_rows_scales_bars_to_peak():
    rows = render._age_rows([
        {"age": "AGE_40", "gender": "FEMALE", "play": 100, "ratio": 24},
        {"age": "AGE_40", "gender": "MALE", "play": 50, "ratio": 12},
    ])
    assert len(rows) == 1
    assert rows[0]["age"] == "40대"
    assert rows[0]["female_w"] == 100.0      # 최대값이 막대 100%
    assert rows[0]["male_w"] == 50.0


def test_age_rows_skips_empty_buckets():
    assert render._age_rows([]) == []


def test_gender_split_uses_play_counts():
    assert render._gender_split([
        {"gender": "FEMALE", "play": 60}, {"gender": "MALE", "play": 40},
    ]) == {"female": 60, "male": 40}
    assert render._gender_split([]) == {"male": 0, "female": 0}


def test_chart_payload_sums_viewer_types():
    p = render._chart_payload([
        {"date": "2026-06-10", "play": 10, "new_user": 6, "revisit_user": 3},
        {"date": "2026-06-11", "play": 20, "new_user": 8, "revisit_user": 4},
    ])
    assert p["labels"] == ["2026-06-10", "2026-06-11"]
    assert p["play"] == [10, 20]
    assert p["viewer"] == [9, 12]


def test_chart_payload_none_when_too_short():
    assert render._chart_payload([{"date": "2026-06-10", "play": 10}]) is None
    assert render._chart_payload([]) is None


def test_chart_payload_none_when_all_zero():
    """클립 0건 계정도 팔로워 추이 때문에 시계열은 존재한다 — 0만 그리지 않는다."""
    assert render._chart_payload([
        {"date": "2026-07-08", "play": 0, "new_user": 0, "revisit_user": 0, "follow": 3},
        {"date": "2026-07-09", "play": 0, "new_user": 0, "revisit_user": 0, "follow": 2},
    ]) is None


def test_render_html_survives_empty_account():
    """업로드 0건 계정(freelife1245)에서 죽으면 안 된다."""
    html = render.render_html([{
        "naver_id": "freelife1245", "name": "빈 계정", "clip_id": "ootd_diver",
        "followers": 0, "clips": [], "daily": [], "entry_points": [], "age_gender": [],
        "totals": None, "recent7": None, "error": None,
    }], NOW)
    assert "빈 계정" in html
    assert "아직 게시된 클립이 없습니다" in html


def test_render_html_shows_relogin_command_on_session_error():
    html = render.render_html([{
        "naver_id": "so_younique", "name": "운동하는 디자이너", "clips": [],
        "daily": [], "entry_points": [], "age_gender": [], "error": "session",
    }], NOW)
    assert "세션이 만료" in html
    assert "src.setup_login so_younique" in html


def test_render_html_escapes_script_in_title():
    """캡션에 </script> 가 들어가도 차트 스크립트가 닫히면 안 된다."""
    html = render.render_html([{
        "naver_id": "x", "name": "x", "clips": [], "entry_points": [], "age_gender": [],
        "daily": [{"date": "2026-06-10", "play": 1}, {"date": "2026-06-11", "play": 2}],
        "error": None,
    }], NOW)
    assert "</script>" not in html.split("const CHART_DATA")[1].split("\n")[0]


def test_expiring_session_banner():
    """세션 잔여가 얼마 없으면 수집이 성공해도 배너로 알린다."""
    html = render.render_html([{
        "naver_id": "funfun_seoki", "name": "물 만난 약사", "clips": [], "daily": [],
        "entry_points": [], "age_gender": [], "error": None,
        "session_days_left": 3.0, "has_credentials": True,
    }], NOW)
    assert "3일 뒤</b> 만료" in html
    assert "src.setup_login funfun_seoki" in html


def test_no_banner_when_session_healthy():
    html = render.render_html([{
        "naver_id": "x", "name": "x", "clips": [], "daily": [],
        "entry_points": [], "age_gender": [], "error": None,
        "session_days_left": 28.0, "has_credentials": True,
    }], NOW)
    assert "만료됩니다" not in html
