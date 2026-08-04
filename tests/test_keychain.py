from src import keychain


def test_missing_account_returns_none():
    assert keychain.get("존재하지-않는-계정-xyz") is None


def test_store_hint_is_runnable_command():
    hint = keychain.store_hint("funfun_seoki")
    assert hint.startswith("security add-generic-password")
    assert "-s naver-clip" in hint
    assert "-a funfun_seoki" in hint


def test_reads_naver_password_through_keychain():
    """naver_login 이 키체인 통로를 그대로 쓰는지 — 저장돼 있으면 읽혀야 한다."""
    from src.naver_login import has_credentials
    assert has_credentials("funfun_seoki") == (keychain.get("funfun_seoki") is not None)
