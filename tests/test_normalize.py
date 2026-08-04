from datetime import datetime

from src import normalize as nz


def ms(day: int) -> int:
    """2026-06-{day} 00:00 KST 의 epoch 밀리초."""
    return int(datetime(2026, 6, day, tzinfo=nz.KST).timestamp() * 1000)


D10, D12 = ms(10), ms(12)


def test_to_date_kst():
    assert nz.to_date(D10) == "2026-06-10"
    assert nz.to_date(None) is None


def test_daily_series_merges_data_types_by_date():
    rows = nz.daily_series(
        {"playCount": [{"date": D10, "count": 100}]},
        {"newUser": [{"date": D10, "count": 60}],
         "revisitingUser": [{"date": D10, "count": 40}]},
        {"contribution": [{"date": D10, "count": 2}]},
        {"dailyData": [{"date": D10, "count": 3}]},
    )
    assert rows == [{"date": "2026-06-10", "play": 100, "new_user": 60,
                     "revisit_user": 40, "follow_contribution": 2, "follow": 3}]


def test_daily_series_fills_missing_days_with_zero():
    """API는 활동이 0인 날을 응답에서 빼므로 x축이 왜곡된다 — 0으로 메워야 한다."""
    rows = nz.daily_series(
        {"playCount": [{"date": D10, "count": 5}, {"date": D12, "count": 7}]},
        {}, {},
    )
    assert [r["date"] for r in rows] == ["2026-06-10", "2026-06-11", "2026-06-12"]
    assert [r["play"] for r in rows] == [5, 0, 7]


def test_daily_series_empty():
    assert nz.daily_series({}, {}, {}) == []


def test_clip_title_uses_first_line():
    assert nz.clip_title("마스크 유막제거\n\n본문입니다\n#해시태그") == "마스크 유막제거"
    assert nz.clip_title("") == "(제목 없음)"
    assert nz.clip_title(None) == "(제목 없음)"


def test_clip_record_flattens_category():
    rec = nz.clip_record({
        "mediaContentNo": 1, "videoId": "V", "description": "제목\n본문",
        "category": {"firstCategory": "OUTDOOR", "secondCategory": "WATERACTIVITIES"},
        "registerDateTime": "2026-07-24T17:22:20.000+09:00", "playCount": 292, "likeCount": 3,
    })
    assert rec["no"] == 1
    assert rec["title"] == "제목"
    assert rec["category"] == "OUTDOOR/WATERACTIVITIES"
    assert rec["deleted"] is False


def test_merge_clips_preserves_deleted():
    """삭제된 클립은 목록에서 사라지지만 성과는 남겨야 한다."""
    stored = [{"no": 1, "play": 900, "posted_at": "2026-06-01", "deleted": False},
              {"no": 2, "play": 100, "posted_at": "2026-07-01", "deleted": False}]
    fresh = [{"no": 2, "play": 150, "posted_at": "2026-07-01", "deleted": False}]

    out = nz.merge_clips(stored, fresh, "2026-08-05T05:00:00+09:00")

    by_no = {c["no"]: c for c in out}
    assert by_no[1]["deleted"] is True
    assert by_no[1]["play"] == 900          # 마지막으로 본 성과를 유지
    assert by_no[2]["deleted"] is False
    assert by_no[2]["play"] == 150          # 살아있는 클립은 최신값
    assert by_no[2]["last_seen"] == "2026-08-05T05:00:00+09:00"


def test_merge_clips_sorts_newest_first():
    out = nz.merge_clips([], [{"no": 1, "posted_at": "2026-06-01"},
                              {"no": 2, "posted_at": "2026-07-01"}], "now")
    assert [c["no"] for c in out] == [2, 1]


def test_summary_flattens_counted_nodes():
    s = nz.summary(
        {"playCount": {"count": 1109, "diffRate": 18.5, "diffRateType": "DOWN"},
         "uniqueUser": {"count": 810}},
        {"exposureCount": 1419, "clickCount": 89, "clickRate": 6.3},
    )
    assert s["play"] == {"count": 1109, "diff_rate": 18.5, "diff_type": "DOWN"}
    assert s["unique_user"]["count"] == 810
    assert (s["exposure"], s["click"], s["click_rate"]) == (1419, 89, 6.3)


def test_summary_tolerates_empty_payload():
    s = nz.summary({}, {})
    assert s["play"]["count"] is None
    assert s["exposure"] is None


def test_entry_points_and_age_gender():
    assert nz.entry_points({"entryPointPlayCounts": [
        {"entryPoint": "네이버 홈", "playCount": 1026, "ratio": 92.5}]}) == [
        {"name": "네이버 홈", "play": 1026, "ratio": 92.5}]
    assert nz.age_gender({"ageGenderRatioSet": {"ageGenderRatios": [
        {"age": "AGE_40", "gender": "FEMALE", "playCount": 258, "ratio": 24}]}}) == [
        {"age": "AGE_40", "gender": "FEMALE", "play": 258, "ratio": 24}]
    assert nz.entry_points({}) == []
    assert nz.age_gender({}) == []
