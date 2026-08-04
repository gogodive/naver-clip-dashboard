"""macOS 키체인에서 비밀값을 읽는다.

비밀번호·토큰을 파일이나 환경변수로 두지 않기 위한 유일한 통로다.
저장은 사람이 직접 한다(대화형 입력이라 셸 히스토리에도 남지 않는다):

    security add-generic-password -s naver-clip -a <이름> -w
"""

from __future__ import annotations

import subprocess

SERVICE = "naver-clip"


def get(account: str) -> str | None:
    """키체인에서 값을 읽는다. 없거나 접근 실패하면 None. 값은 로그에 남기지 않는다."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    value = r.stdout.rstrip("\n")
    return value or None


def store_hint(account: str) -> str:
    return f"security add-generic-password -s {SERVICE} -a {account} -w"
