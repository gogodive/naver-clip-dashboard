import socket

from src import clipapi, notify


def test_wait_for_network_true_when_dns_resolves(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [("ok",)])
    assert clipapi.wait_for_network(timeout_s=1, interval_s=0)


def test_wait_for_network_retries_then_succeeds(monkeypatch):
    """절전에서 막 깨어나 DNS 가 늦게 붙는 경우 — 몇 번 실패 후 살아나야 한다."""
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise socket.gaierror(8, "nodename nor servname provided")
        return [("ok",)]

    monkeypatch.setattr(socket, "getaddrinfo", flaky)
    monkeypatch.setattr(clipapi.time, "sleep", lambda s: None)
    assert clipapi.wait_for_network(timeout_s=60, interval_s=0)
    assert calls["n"] == 3


def test_wait_for_network_gives_up(monkeypatch):
    def dead(*a, **k):
        raise socket.gaierror(8, "down")

    monkeypatch.setattr(socket, "getaddrinfo", dead)
    monkeypatch.setattr(clipapi.time, "sleep", lambda s: None)
    assert not clipapi.wait_for_network(timeout_s=0, interval_s=0)


def test_notify_escapes_quotes(monkeypatch):
    """메시지에 따옴표가 있어도 AppleScript 가 깨지면 안 된다 — 경보가 안 뜨면 끝이다."""
    seen = {}

    class R:
        returncode = 0

    def fake_run(cmd, **k):
        seen["script"] = cmd[2]
        return R()

    monkeypatch.setattr(notify.subprocess, "run", fake_run)
    assert notify.mac('제목 "A"', '본문 "B" \\ 끝')
    assert '\\"A\\"' in seen["script"]
    assert '\\"B\\"' in seen["script"]


def test_notify_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("osascript 없음")

    monkeypatch.setattr(notify.subprocess, "run", boom)
    assert notify.mac("t", "m") is False
