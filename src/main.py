"""엔트리포인트: 수집 → data/*.json 갱신 → site/index.html 생성 → 노션 상태 기록."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import keychain
from src.collect import collect_all, load_config
from src.notion_status import build_status, update_callout
from src.render import render_html

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).parent.parent
NOTION_KEYCHAIN_ACCOUNT = "notion-token"


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = load_config(ROOT / "config.yaml")
    profiles_dir = (ROOT / config["profiles_dir"]).resolve()
    now = datetime.now(KST)

    accounts = collect_all(config, profiles_dir, ROOT / "data", now)

    # GitHub Pages 를 main 브랜치의 /docs 에서 서빙한다 (로컬 실행이라 Actions 없이 배포)
    site = ROOT / "docs"
    site.mkdir(exist_ok=True)
    (site / "index.html").write_text(render_html(accounts, now), encoding="utf-8")
    (site / ".nojekyll").touch()

    icon, status = build_status(accounts, now)
    print(f"완료: {icon} {status} → docs/index.html")

    # 노션 상태 기록은 부가 기능 — 실패해도 수집/배포를 막지 않는다
    # 토큰은 키체인이 우선, 없으면 환경변수(.env)
    notion_token = keychain.get(NOTION_KEYCHAIN_ACCOUNT) or os.environ.get("NOTION_TOKEN")
    page_id = config.get("notion", {}).get("hub_page_id")
    if notion_token and page_id:
        if update_callout(notion_token, page_id, icon, status):
            print("노션 상태 콜아웃 갱신 완료")
        else:
            print("노션 콜아웃 갱신 실패 — 통합이 허브 페이지에 연결됐는지 확인하세요")
    else:
        print(f"노션 토큰 없음 — 상태 기록 건너뜀 "
              f"({keychain.store_hint(NOTION_KEYCHAIN_ACCOUNT)})")

    # 세션 만료는 사람이 손대야 풀린다 — 종료 코드로도 알린다
    return 2 if any(a.get("error") == "session" for a in accounts) else 0


if __name__ == "__main__":
    sys.exit(main())
