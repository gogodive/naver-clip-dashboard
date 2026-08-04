from datetime import datetime, timedelta, timezone

from src.notion_status import build_status

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 8, 5, 5, 0, tzinfo=KST)


def acc(naver_id, error=None, clips=0):
    return {"naver_id": naver_id, "error": error, "clips": [{}] * clips}


def test_all_ok():
    icon, text = build_status([acc("a", clips=2), acc("b", clips=3)], NOW)
    assert icon == "✅"
    assert "2026-08-05 05:00 갱신 완료" in text
    assert "2개 계정" in text
    assert "클립 5개" in text


def test_session_expiry_is_loudest_and_shows_command():
    """세션 만료는 사람이 재로그인해야만 풀린다 — 명령어까지 알려줘야 한다."""
    icon, text = build_status([acc("a"), acc("so_younique", error="session")], NOW)
    assert icon == "🚨"
    assert "so_younique 세션 만료" in text
    assert "src.setup_login so_younique" in text
    assert "1/2개 계정" in text


def test_fetch_failure_is_warning():
    icon, text = build_status([acc("a"), acc("b", error="fetch")], NOW)
    assert icon == "⚠️"
    assert "실패: b" in text


def test_session_expiry_outranks_fetch_failure():
    icon, _ = build_status([acc("a", error="fetch"), acc("b", error="session")], NOW)
    assert icon == "🚨"
