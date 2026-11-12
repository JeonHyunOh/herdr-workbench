#!/bin/bash
# 레포(또는 워크트리)의 팀 스킬을 Codex가 읽게 한다.
#   .agents/skills/<이름> → ../../.claude/skills/<이름> 스킬별 상대 링크를 만든다.
#   링크가 아닌 사본(Codex 'Claude 설정 가져오기'가 만든 것)은 백업 폴더로 옮긴다.
#   팀에서 지운 스킬의 끊어진 링크는 지운다.
#   .git/info/exclude(워크트리와 공유)에 .agents/ .codex/ 를 더한다.
# 폴더 통째 링크를 쓰지 않는 이유: 가져오기(COMMANDS)가 .agents/skills 안에 쓰면 팀 폴더로 새어 들어간다.
# 사용: link-repo-skills.sh <레포 경로> [--dry-run]
# 기록: 2026-11-09 2번 허브 하네스 정리(_my/docs/workspace/2026-11-09-hub-harness-candidates.md H3-2)
set -euo pipefail

R=$(cd "$1" && pwd)
DRY=${2:-}
run() { if [ "$DRY" = "--dry-run" ]; then echo "  would: $*"; else "$@"; fi; }

if [ ! -d "$R/.claude/skills" ]; then
  echo "팀 스킬 없음, 건너뜀: $R"
  exit 0
fi
if [ -n "$(git -C "$R" ls-files .agents | head -1)" ]; then
  echo "중단: .agents 가 git에 추적되고 있다 ($R). 팀 결정 없이 바꾸지 않는다."
  exit 1
fi

A="$R/.agents/skills"
BK="$HOME/.config/harness-backups/$(date +%F)/repo-skills/$(basename "$R")"
run mkdir -p "$A"

moved=0; cleaned=0; linked=0
for e in "$A"/*; do
  [ -e "$e" ] || [ -L "$e" ] || continue
  n=$(basename "$e")
  if [ -L "$e" ]; then
    if [ ! -e "$e" ]; then run rm "$e"; cleaned=$((cleaned + 1)); fi
    continue
  fi
  run mkdir -p "$BK"
  if [ -e "$BK/$n" ]; then run mv "$e" "$BK/$n.$(date +%H%M%S)"; else run mv "$e" "$BK/$n"; fi
  moved=$((moved + 1))
done

for d in "$R/.claude/skills"/*/; do
  n=$(basename "$d")
  if [ ! -e "$A/$n" ] || { [ "$DRY" = "--dry-run" ] && [ ! -L "$A/$n" ]; }; then
    run ln -s "../../.claude/skills/$n" "$A/$n"
    linked=$((linked + 1))
  fi
done

GD=$(cd "$R" && cd "$(git rev-parse --git-common-dir)" && pwd)
EX="$GD/info/exclude"
for pat in ".agents/" ".codex/"; do
  if ! grep -qxF "$pat" "$EX" 2>/dev/null; then
    if [ "$DRY" = "--dry-run" ]; then echo "  would: append '$pat' to $EX"; else mkdir -p "$GD/info"; echo "$pat" >> "$EX"; fi
  fi
done

echo "$(basename "$R"): 사본 백업 $moved · 끊어진 링크 정리 $cleaned · 새 링크 $linked${DRY:+ (미리보기)}"
