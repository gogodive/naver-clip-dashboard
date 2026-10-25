from datetime import datetime, timedelta, timezone

from src.notion_status import build_status

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 8, 5, 5, 0, tzinfo=KST)


def acc(naver_id, error=None, clips=0, days_left=None, creds=True):
    return {"naver_id": naver_id, "error": error, "clips": [{}] * clips,
            "session_days_left": days_left, "has_credentials": creds}


def test_relogin_failed_warns_with_manual_command():
    """비밀번호가 있는데도 잔여가 낮게 남았다면 선제 재로그인이 실패한 것이다."""
    icon, text = build_status([acc("a", clips=1, days_left=28),
                               acc("b", clips=1, days_left=3)], NOW)
    assert icon == "⚠️"
    assert "자동 재로그인 실패: b" in text
    assert "src.setup_login b" in text


def test_no_naver_credentials_is_a_quiet_choice():
    """네이버 비밀번호를 저장하지 않는 것은 사용자가 고른 운영 방식이다(2026-10).

    매일 쓰는 한 서버는 쿠키 기한이 지나도 세션을 받아준다. 그러니 기한 경과만으로
    경고하면 매일 헛경보가 된다 — 실제로 한 달 내내 그랬다. 끊긴 날(401)에만 알린다.
    """
    icon, text = build_status([acc("a", clips=1, days_left=-26, creds=False),
                               acc("b", clips=1, days_left=-26, creds=False)], NOW)
    assert icon == "✅"
    assert "키체인" not in text
    assert "만료" not in text


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
    """서버가 세션을 거부하면 사람이 로그인해야 한다 — 명령어까지 알려줘야 한다."""
    icon, text = build_status([acc("a"), acc("so_younique", error="session")], NOW)
    assert icon == "🚨"
    assert "so_younique 세션 끊김" in text
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
