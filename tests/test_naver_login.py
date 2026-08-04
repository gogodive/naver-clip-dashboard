import json
import time

from src.naver_login import days_until_expiry


def write_cookies(tmp_path, cookies):
    (tmp_path / "session_cookies.json").write_text(json.dumps(cookies))
    return tmp_path


def test_days_until_expiry_reads_nid_aut(tmp_path):
    d = write_cookies(tmp_path, [
        {"name": "NID_AUT", "expires": time.time() + 10 * 86400},
        {"name": "NID_SES", "expires": -1},
    ])
    assert 9.9 < days_until_expiry(d) < 10.1


def test_session_cookie_counts_as_already_expired(tmp_path):
    """'로그인 상태 유지'가 꺼진 채 로그인하면 NID_AUT 가 세션 쿠키다 — 하루도 못 간다."""
    d = write_cookies(tmp_path, [{"name": "NID_AUT", "expires": -1}])
    assert days_until_expiry(d) == 0.0


def test_none_when_no_snapshot(tmp_path):
    assert days_until_expiry(tmp_path) is None


def test_none_when_nid_aut_absent(tmp_path):
    d = write_cookies(tmp_path, [{"name": "NNB", "expires": time.time() + 86400}])
    assert days_until_expiry(d) is None


def test_none_on_corrupt_snapshot(tmp_path):
    (tmp_path / "session_cookies.json").write_text("{ not json")
    assert days_until_expiry(tmp_path) is None


def test_expired_cookie_is_negative(tmp_path):
    d = write_cookies(tmp_path, [{"name": "NID_AUT", "expires": time.time() - 2 * 86400}])
    assert days_until_expiry(d) < -1
