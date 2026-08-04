from datetime import datetime, timedelta, timezone

from src.notion_status import build_status

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 8, 5, 5, 0, tzinfo=KST)


def acc(naver_id, error=None, clips=0, days_left=None):
    return {"naver_id": naver_id, "error": error, "clips": [{}] * clips,
            "session_days_left": days_left}


def test_expiring_session_warns_even_when_collection_succeeded():
    """수집이 됐어도 세션이 곧 끊기면 알려야 한다 — 선제 재로그인이 실패했다는 뜻."""
    icon, text = build_status([acc("a", clips=1, days_left=28),
                               acc("b", clips=1, days_left=3)], NOW)
    assert icon == "⚠️"
    assert "세션 만료 임박: b(3일)" in text
    assert "src.setup_login b" in text


def test_healthy_session_does_not_warn():
    icon, _ = build_status([acc("a", clips=1, days_left=28)], NOW)
    assert icon == "✅"


def test_all_ok():
    icon, text = build_status([acc("a", clips=2), acc("b", clips=3)], NOW)
    assert icon == "✅"
    assert "2026-08-05 05:00 갱신 완료" in text
    assert "2개 계정" in text
    assert "클립 5개" in text


def test_session_expiry_is_loudest_and_shows_command():
    """자동 재로그인까지 실패했다면 사람이 손대야 한다 — 명령어까지 알려줘야 한다."""
    icon, text = build_status([acc("a"), acc("so_younique", error="session")], NOW)
    assert icon == "🚨"
    assert "so_younique 자동 재로그인 실패" in text
    assert "src.setup_login so_younique" in text
    assert "1/2개 계정" in text


def test_fetch_failure_is_warning():
    icon, text = build_status([acc("a"), acc("b", error="fetch")], NOW)
    assert icon == "⚠️"
    assert "실패: b" in text


def test_session_expiry_outranks_fetch_failure():
    icon, _ = build_status([acc("a", error="fetch"), acc("b", error="session")], NOW)
    assert icon == "🚨"


def test_captcha_challenge_outranks_everything():
    """캡차·2차 인증은 자동화로 못 넘는다 — 가장 먼저 알려야 한다."""
    icon, text = build_status(
        [acc("a", error="fetch"), acc("b", error="session"), acc("c", error="challenge")], NOW)
    assert icon == "🚨"
    assert "캡차/2차 인증" in text
    assert "src.setup_login c" in text
    assert "0/3개 계정" in text
