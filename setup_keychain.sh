#!/bin/bash
# 키체인에 네이버 비밀번호 3개 + 노션 토큰을 (다시) 저장한다.
# 맥 로그인 비밀번호를 재설정하면 macOS가 키체인을 초기화한다 — 그때마다 이걸 다시 실행하면 된다.
# 입력값은 화면에 보이지 않으며, 파일·셸 히스토리 어디에도 남지 않는다.
set -u

for a in freelife1245 so_younique funfun_seoki; do
  echo
  echo "▶ [$a] 네이버 로그인 비밀번호를 두 번 입력하세요 (화면에 안 보이는 게 정상)"
  security add-generic-password -U -s naver-clip -a "$a" -w || echo "  !! $a 저장 실패"
done

echo
echo "▶ [notion-token] 노션 통합 시크릿(ntn_ 로 시작)을 두 번 붙여넣으세요"
echo "   https://www.notion.so/my-integrations → 쓰던 통합 → 시크릿 복사"
security add-generic-password -U -s naver-clip -a notion-token -w || echo "  !! notion-token 저장 실패"

echo
echo "=== 확인 ==="
for a in freelife1245 so_younique funfun_seoki notion-token; do
  security find-generic-password -s naver-clip -a "$a" >/dev/null 2>&1 \
    && echo "  $a: 저장됨" || echo "  $a: 없음"
done
