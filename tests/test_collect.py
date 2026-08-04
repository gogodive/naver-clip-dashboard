from src.collect import should_relogin

THRESHOLD = 5


def test_fires_inside_window():
    """만료가 임박하면 아직 쓸 수 있을 때 미리 갈아 끼워야 한다."""
    assert should_relogin(3.0, THRESHOLD, has_creds=True)
    assert should_relogin(5.0, THRESHOLD, has_creds=True)


def test_quiet_outside_window():
    """평상시에는 건드리지 않는다 — 불필요한 로그인이 캡차를 부른다."""
    assert not should_relogin(29.0, THRESHOLD, has_creds=True)
    assert not should_relogin(5.1, THRESHOLD, has_creds=True)


def test_fires_when_already_expired():
    """세션 쿠키(0일)나 이미 지난 경우에도 재로그인해야 한다."""
    assert should_relogin(0.0, THRESHOLD, has_creds=True)
    assert should_relogin(-3.0, THRESHOLD, has_creds=True)


def test_skips_without_credentials():
    """비밀번호가 없으면 시도해도 실패한다 — 조용히 넘기고 사람에게 알린다."""
    assert not should_relogin(1.0, THRESHOLD, has_creds=False)


def test_skips_when_never_logged_in():
    """스냅샷이 없으면 수집을 시도해 MissingSession 경로로 처리한다."""
    assert not should_relogin(None, THRESHOLD, has_creds=True)
    assert not should_relogin(None, THRESHOLD, has_creds=False)
