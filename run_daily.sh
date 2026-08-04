#!/bin/bash
# 매일 05:00 launchd 가 실행한다. 수집 → 렌더 → 커밋 → 푸시.
# 세션이 만료돼도 중단하지 않는다 — 대시보드에 경고 배너를 띄운 채로 배포한다.
set -uo pipefail

cd "$(dirname "$0")" || exit 1
mkdir -p logs

# NOTION_TOKEN 등 (git 에 올라가지 않는 파일)
[ -f .env ] && set -a && . ./.env && set +a

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 시작 ====="

.venv/bin/python -m src.main
STATUS=$?
if [ $STATUS -eq 2 ]; then
  echo "경고: 세션이 만료된 계정이 있습니다 — setup_login 이 필요합니다"
elif [ $STATUS -ne 0 ]; then
  echo "오류: 수집 실패 (exit $STATUS) — 커밋을 건너뜁니다"
  exit $STATUS
fi

git add data docs
if git diff --cached --quiet; then
  echo "변경 없음 — 커밋 건너뜀"
else
  git commit -m "chore: 일일 데이터 갱신 $(date '+%Y-%m-%d')" || true
fi

git pull --rebase origin main && git push origin main
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 완료 (exit $STATUS) ====="
exit $STATUS
