"""맥 알림 — 키체인·노션과 무관한 마지막 경보 통로.

노션 콜아웃은 키체인의 토큰이 있어야 갱신된다. 키체인이 초기화되면 경보 통로도
같이 죽어서 콜아웃이 마지막 ✅ 에 멈춘 채 아무도 모르게 된다(2026-09 실제로 일주일간 발생).
그래서 비밀값이 전혀 필요 없는 알림을 하나 더 둔다.
"""

from __future__ import annotations

import subprocess


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def mac(title: str, message: str) -> bool:
    """알림 센터에 알림을 띄운다. 성공 여부 반환(실패해도 예외를 던지지 않는다)."""
    script = (f'display notification "{_q(message)}" '
              f'with title "{_q(title)}" sound name "Basso"')
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0
