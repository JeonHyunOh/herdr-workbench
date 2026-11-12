# 작업대 v1

진짜 Claude Code·Codex TUI를 Herdr에서 열고 부모별 수신함과 워크트리 수명주기를 관리한다.

설정은 `bench.yaml` 하나다. Herdr도 직접 읽도록 JSON 문법인 YAML로 저장한다. 모든 경로는 절대 경로다. Python 3와 PyYAML 6이 필요하다. `python3 -m pip install -r requirements.txt`는 필요한 환경에서만 실행한다.

```sh
python3 bench.py --help
python3 bench.py spawn --role secretary --vendor claude --model claude-opus-5-5 --cwd /path/to/hub
python3 bench.py spawn --role lead --task '범위와 완료 조건'
python3 bench.py spawn --role worker-code --vendor codex --model gpt-6.1-sol --worktree /path/to/repo task-branch --task '작업 지시'
python3 bench.py report --summary '결과·검증·남은 판단' --complete
python3 bench.py inbox
python3 bench.py ack --report REPORT_ID
python3 bench.py wait --timeout 60
python3 bench.py inspect
python3 bench.py close CHILD_TERMINAL
python3 bench.py discard WORKTREE_PATH
python3 bench.py send CHILD_TERMINAL '후속 지시' [--if idle|working]
python3 bench.py ls [--json] [--all]
python3 bench.py rename TERMINAL --display 이름
python3 bench.py retitle
python3 bench.py wait --timeout 3600 --from CHILD_TERMINAL
```

`send`는 등록된 부모가 자기 직계 자식에게만 후속 지시를 보낸다. 내부에서 `hc send --json [--if …] -- <자식> <글>`을 부른다. `--`가 있어 `-`로 시작하는 글도 그대로 간다(맨 `hc send`는 이런 글을 옵션으로 읽고 거절한다). `--force`는 쓰지 않으므로 승인 대화상자에 멈춘 화면에는 쓰지 않는다. hc가 사람이 타이핑을 멈출 때까지 기다리는 동안 수신함 잠금을 잡지 않는다. 보낸 글·해시·hc 응답은 `state.json`의 `directives`에 남고 `inspect`로 볼 수 있다. 지시는 보고가 아니므로 수신함 미확인 점을 만들지 않는다. 실패나 시간 초과는 기록만 하고 다시 보내지 않는다. 다시 보내기 전에 `hc read`로 화면을 본다.

`ls`는 등록된 세션을 부모 → 자식 순서의 들여쓴 트리로 한 줄씩 보여 준다. 각 줄에 표시 이름, 역할·모델, hc 실시간 상태(`live/working` 등), 미확인 보고 수, 워크트리 브랜치가 나온다. hc에 없으면 `not listed`, hc 호출이 실패하면 `unknown`으로 적고 기록은 그대로 보인다. 막 뜬 터미널처럼 hc가 status를 주지 않으면 비워 둔다. `--json`은 같은 내용을 목록으로, `--all`은 닫힌 세션까지 보인다. `hc ls`를 즉석 파이썬으로 읽지 않는다.

Herdr 위쪽 탭 줄의 이름도 표시 이름을 따른다. `spawn`은 새 세션의 탭이 나타나면(최대 5초 대기) 그 탭 이름을 `--display`(없으면 `--name`)로 바꾼다. 이미 열린 세션은 `retitle`로 한 번에 맞춘다. 바꾸는 탭은 Herdr가 번호로 자동 이름을 붙인 탭과, 그 세션의 예전 이름이 남은 탭뿐이다. 사람이 붙인 이름은 두고 바꿀 명령(`herdr-app do tab.rename …`)만 돌려준다. 이 기능은 설정의 `herdr_app` 경로가 있을 때만 켜진다(테스트 설정에는 없어 실제 창을 건드리지 않는다). 앱이 없거나 늦어도 spawn은 실패하지 않고 결과를 노드의 `tab_title`에 남긴다.

`rename <대상> --display <이름>`은 자기 자신이나 직계 자식의 표시 이름을 바꾼다. hc 라벨 `bench.display`(트리가 쓰는 이름)를 먼저 바꾸고, 성공해야 bench 기록과 `display_history`를 고친다. Claude 세션 이름(`/rename`)과 Herdr 탭 이름(hc의 `where`)은 사람 화면이라 바꾸지 않고, 그 탭 id를 넣은 `herdr-app do tab.rename …` 명령을 `manual_steps`로 돌려준다.

`wait --timeout`은 0~3600초다. Claude 세션은 Bash 기본 시간 한도가 120초이므로 120초를 넘게 기다릴 때는 백그라운드로 실행한다(보고가 오면 명령이 끝나 세션이 깨어난다). `--from <자식>`을 주면 그 자식의 보고만 깨운다. 이때 `reports`는 그 자식 것만, `pending_report_count`·`pending_report_ids`는 모든 미확인 보고를 센다. 출력을 셸 변수에 담아 다시 넘길 때 zsh의 `echo "$out"`은 JSON 안의 `\n`을 실제 줄바꿈으로 바꿔 JSON을 깨뜨린다(11/10 디렉터가 겪은 'Invalid control character'의 원인). `printf '%s' "$out"`을 쓰거나 바로 파이프로 넘긴다.

`spawn --task`와 `send`는 글 속 날짜·요일 표기(`11/14(금)`, `2026-11-14(금)`, `11월 14일 금요일`, `11/9 월,` 등)를 KST 달력과 대조한다. 어긋나면 아무것도 실행·기록하지 않고 거절한다. 연도가 없으면 오늘과 가장 가까운 해로 본다. 맨 '일'은 명사와 헷갈려 괄호나 '요일'이 붙을 때만 요일로 읽는다. 의도한 표기면 `--allow-date-mismatch`를 붙인다. 새 세션의 첫 메시지에는 역할 지시문 뒤, 작업 앞에 `[작업대 달력]` 한 줄(오늘·이번 주 7일·다음 주 월요일)이 붙는다.

`report`(MCP `bench_report`도)는 본문 첫 줄의 'HH:MM' 표기가 보낸 시각(KST)보다 5분 넘게, 90분 안으로 늦으면 거절한다(B16). `15:5x`처럼 x가 있으면 가장 이른 값(15:50)으로 읽는다. 첫 줄의 마감·계획(`까지`·`기한`·`예정`·`예약`·`쯤`, `끝낼 시각 …`), 다른 날짜 뒤 시각, 따옴표 안 인용, `T…Z` UTC 표기는 보지 않는다. 의도한 표기면 `--allow-late-time`(MCP `allow_late_time`). 보낸 시각은 기록의 `sent_kst`(예: `11/11(수) 15:46 KST`)에 붙는다. 머리에 시각을 쓰지 않아도 된다.

`HC_TERMINAL_ID`가 호출자다. 자식은 등록된 부모가 만들고, 보고 대상은 등록된 부모로 고정된다. `--parent`는 호출자와 같아야 한다. 운영자의 작업 없는 점검에만 `--no-task --parent`로 계층을 만들 수 있다. 작업자는 `worker-code`, `worker-review`, `worker-query` 중 고른다. Codex 작업자는 보고용 MCP의 `bench_report`, `bench_inbox`, `bench_ack`도 쓸 수 있다. MCP는 세션 생성이나 임의 수신자 전송을 제공하지 않는다.

Codex MCP가 `HC_TERMINAL_ID`를 받지 못하면 bench는 프로세스 조상에서 등록된 Codex를 찾고, 그 실행 파일을 `vendors.codex.process_executable`과 대조한다. 맞지 않으면 신원을 거절한다. 실행 파일은 리눅스에서 `/proc/<pid>/exe`(심볼릭 링크를 모두 푼 경로라 설정값도 풀어서 대조한다), 맥에서는 `ps -o comm=`의 전체 경로를 그대로 대조한다(B28 2026-11-12. 리눅스 `ps`는 이름만 줘서 맞은 적이 없었다). 시험은 `tests/test_process_linux.py`다.

`wait`는 `ready`와 `timeout` 모두 실제 미확인 `reports`, `pending_report_count`, `pending_report_ids`, `gate_released`를 반환한다. gate가 닫히면 보고가 있어도 `status=timeout`·`gate_released=false`이며 보고를 지우거나 ack하지 않는다. 다음 단계로 넘어갈지는 `status=ready`를 기준으로 판단한다. `reports`가 비었는지는 별개다.

작업자 샌드박스의 CLI `inspect`도 수신함 `.lock` 쓰기 권한이 필요하다. 접근이 거절되면 해당 경로·쓰기 요구와 MCP 대안을 오류에 표시한다. MCP가 제공된 작업자는 CLI `inspect` 대신 `bench_inbox`·`bench_report`를 쓴다. 이 안내는 샌드박스 권한을 넓히지 않는다.

`spawn --worktree`는 새 로컬 브랜치만 만든다. 기존 브랜치는 인수하지 않는다. 생성 기록은 수신함 `evidence/`와 `state.json`에 남는다. 실패한 실행의 워크트리는 보존하고 기록 경로를 조사한다. 실행 결과가 불명확하면 재실행을 막는다.

세션 이름은 `bench-<역할>-<12자리 고유 id>`다. 같은 역할의 리드·작업자를 여러 개 열어도 hc 이름이 겹치지 않으며, 등록 이름과 Claude 세션 이름에도 같은 값을 쓴다.

`--name`으로 hc 이름을 직접 정할 수 있다. Herdr 규칙대로 영문 소문자·숫자·`-`·`_` 1~32자만 받는다. 한글 같은 다른 글자는 `--display`에 넣는다(1~32자). 표시 이름은 hc 라벨 `bench.display`와 Claude 세션 이름이 되고, 트리는 이 라벨을 hc 이름보다 먼저 보여 준다. 예: `spawn --role secretary --name director1 --display 디렉터`.

`--resume <세션 id>`는 Claude 세션이 기존 대화를 새 터미널에서 이어 열게 한다. 역할 지시문과 작업은 첫 메시지로 붙고, 등록·부모·보고 경로는 새로 연 세션과 같다. 같은 대화가 다른 터미널에 열려 있으면 기록이 섞이므로 원래 터미널을 먼저 닫는다. 이 확인은 도구가 하지 않는다. `--worktree`와 함께 쓸 수 없고 Codex에는 쓸 수 없다.

`close`는 등록된 부모만 호출한다. 자식을 먼저 종료한 뒤 변경·미push·origin/main 확인 실패가 있으면 워크트리를 보존한다. `origin/main`은 매번 fetch한다. 워크트리를 제거한 뒤 정책 정본의 4조건을 확인해 `git branch -d`를 실행한다. 머지되지 않았거나 소유 근거가 부족하면 브랜치를 남기고 부모 수신함에 이유를 쓴다. 원격 브랜치는 지우지 않는다. 기록은 보존하며 재호출은 완료 결과를 반환한다.

API 키 2개는 최종 자식 argv와 native_exec에서 제거한다. TERM은 xterm-256color로 고정한다. 로그인·HOME·벤더 설정을 재지정하지 않는다. native 실행 증거에는 키 존재 여부만 남기며 값은 기록하지 않는다.

검증:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

테스트는 임시 로컬 Git 원격만 쓴다. `config_diff`의 Unix 소켓 검사는 소켓 생성이 허용된 실행 환경이 필요하다.

## 정리 가능한 무시 파일

Git이 무시한 파일 중 다음 산출물만 자동 제거할 수 있다. 추적 파일의 변경은 경로와 관계없이 정리를 막는다.

`node_modules/`, `.venv/`, `venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `dist/`, `build/`, `cdk.out/`, `coverage/`, `.coverage`, `*.tsbuildinfo`, 루트 `.agents/`·`.codex/`, `.claude/settings.local.json`, `.DS_Store`. 목록 밖 파일은 보존하고 보고한다. 각 항목은 실제 Git fixture 시험으로 검증한다.

작업자가 push 전에 `git branch -m`으로 브랜치 이름을 바꿨으면 `close`가 git reflog의 'Branch: renamed refs/heads/<기록 이름> to …' 사슬로 같은 브랜치임을 확인하고 새 이름을 따라간다. 기록에는 `renames`가 남고 결과 이유에 원래 이름이 붙는다. 기록한 이름이 다시 생겼거나 `switch -c`로 다른 브랜치를 만든 경우는 따라가지 않고 두 이름을 적어 보존한다.

Squash 머지는 커밋 계보가 합쳐지지 않아 브랜치가 남는다. 해당 PR 상태를 확인한다. 초기화한 submodule 때문에 worktree remove가 거절되면 강제하지 않고 오류를 보고한다. close가 fetch하는 동안 수신함 잠금을 유지하는 제한이 있다(최대 30초).

## Herdr 업데이트 뒤 트리 재생성

기존 `v3`·`v3-tree`는 보존한다. 새 버전을 검증할 때도 기존 작업대 mod를 덮어쓰지 않고 새 이름으로 복제한다. 다음의 `workbench-tree-next`·`workbench-next`는 아직 없는 이름으로 고른다.

```sh
herdr-app do mod.clone '{"name":"agents","as":"workbench-tree-next"}'
herdr-app do layout.clone '{"name":"main","as":"workbench-next"}'
cp ~/.config/herdr-app/mods/workbench-tree-next/main.js /tmp/workbench-agents-source.js
python3 build_tree_superset.py --source /tmp/workbench-agents-source.js --output ~/.config/herdr-app/mods/workbench-tree-next/main.js --config bench.yaml
```

새 레이아웃의 `content.mod: agents`만 새 mod 이름으로 바꾼다. 생성기는 기준 코드의 변경 위치가 정확히 1개씩 맞는지 확인한다. Herdr 변경으로 위치가 달라졌으면 중단하고 설치판 코드를 비교한다. `upstream/`은 0.1.13 복제 원본이며 델타 회귀 시험의 기준이다.

```sh
herdr-app check ~/.config/herdr-app/mods/workbench-tree-next
herdr-app status
node tests/test_tree_superset.mjs
herdr-app do workbench-tree-next.dump
```

현재 mod는 `workbench-tree`다. `dump`는 실제 터미널 스냅샷을 수신함의 `mod-state.json`으로 저장한다. 머리글의 `source: herdr.mod.terminals`와 각 노드의 접힘·가시성·native_blocked·unread_count를 확인한다. 실 터미널이 없으면 dump를 만들지 않는다. 모의 렌더 시험은 실제 GUI 확인을 대신하지 않는다. 수신함·설정은 2초 간격으로 읽고 변경됐을 때만 다시 그린다. 기존 일반 에이전트 목록도 유지한다.

## 재부팅 뒤 할 일 (recover, B21 2026-11-11)

맥북을 다시 켰거나 Herdr core가 꺼져 bench 세션이 다 끝났으면, 허브의 아무 터미널에서 먼저 미리보기를 본다.

```sh
python3 /home/you/Project/work/hub/_my/tools/workbench/bench.py --config /home/you/Project/work/hub/_my/tools/workbench/bench.yaml recover --dry-run
```

표에 세션마다 터미널 상태와 할 일이 나온다. 문제가 없으면 같은 줄에서 `--dry-run`을 빼고 실행한다.

- `running`(에이전트가 돌고 있음)은 건너뛴다. `parked`(일부러 멈춤, `bench park <주소>`)와 닫힌 세션도 열지 않는다.
- `shell`(같은 주소에 셸만 되살아남): bench 터미널은 hc의 keep으로 열려 있어, 프로그램이 사라지면 같은 주소에 셸이 남는다. recover는 그 셸에 `exec python3 bench.py --config … relaunch` 1줄을 넣는다. `relaunch`는 그 터미널의 HC_TERMINAL_ID로 자기 기록을 찾아 같은 대화로 다시 뜬다(Claude는 `--resume <session_id>`, Codex는 새 대화로 시작하고 `state_file`을 먼저 읽는다). 주소·부모·자식·워크트리·수신함이 그대로다. 위에서부터 하나씩 열고, 에이전트가 뜨는 것을 확인한 뒤 다음으로 간다.
- `finished`·`not_found`(터미널이 사라짐): `last-alive.json`(bench가 ls·report 때 기록하는 '마지막으로 에이전트가 돌던 세션')에 없던 것은 정전 전에 이미 끝난 것으로 보고 열지 않는다. 디렉터는 takeover로 연다. 그 아래 자식은 안 A(11/11 21:37 운영자 결정)로 연다(`recover-child`): recover 안에서만, 트리의 어느 에이전트도 돌고 있지 않을 때만, 같은 실행에서 부모가 먼저 다시 열렸을 때만 등록된 부모가 아닌 운영자 터미널이 이어받는다. 새 기록에 `recovered_by`·`recovery_id`를 남긴다. 하나라도 어기면 열지 않는다(돌고 있는 에이전트가 있으면 `decide`로 남기고 그 부모가 `bench takeover`로 연다). recover 밖의 takeover 규칙(등록된 부모만)은 그대로다.
- 되살아난 셸에 넣는 글은 `exec python3 bench.py --config … relaunch` 1줄로 고정이다. 그 주소 터미널의 라벨(`herdr.space`·`bench.role`)과 이름이 기록과 하나라도 다르면 어떤 셸에도 넣지 않고 전체를 멈춘다.
- 같은 주소에 라벨이 다른 터미널이 있으면 아무것도 하지 않고 멈춘다. 하나라도 실패하면 거기서 멈추고 연 것·남은 것·실패 이유와 수신함을 되돌리는 `cp` 명령을 출력한다. 실행 전 `state.json`·`view.json`은 `mailbox/backups/`에 복사한다.
- 승인·trust 창은 recover가 답하지 않는다. 새로 뜬 세션이 창을 띄우면 운영자가 직접 답한다.
- 세션 id: 새로 여는 Claude 세션은 bench가 `--session-id`로 id를 정해 기록한다. 그 전에 연 세션은 기록의 `resumed_session` 또는 시작 폴더의 대화 기록에서 제목(표시 이름)이 하나만 맞는 것을 쓴다. Codex 세션은 `spawn --state-file <절대 경로>`나 `bench state-file <경로> [--target 자식]`으로 상태 파일을 남겨야 다시 열린다.

## 트리 전용 파일 tree.json (U6 2026-11-11)

Herdr mod의 `readTextFile`은 1 MiB까지만 읽는다. `view.json`은 보고를 모두 담아 11/11 09:31에 1 MiB를 넘었고, 그 뒤 트리는 bench 기록을 읽지 못해 역할·모델·안 읽은 점이 모두 꺼졌다. bench는 커밋마다 `tree.json`(열린 세션과 트리가 쓰는 필드만, 수 KB)을 함께 쓰고, 트리 mod는 이것을 먼저 읽고 없으면 `view.json`으로 돌아간다.

## 세션을 연 폴더 이름 (B25 2026-11-12)

`tree.json`과 `bench ls`는 줄마다 `folder`를 싣는다. 세션을 연 폴더의 이름만 쓰고 경로·브랜치는 쓰지 않는다(11/12 15:19 운영자). 작업대 워크트리나 레포의 `.claude/worktrees` 아래에서 연 세션은 그 워크트리가 속한 레포 이름(team-repo 등), 그 밖에는 연 폴더의 마지막 이름이다. 그래서 레포 바로 아래에서 연 세션은 레포 이름, 허브에서 연 세션은 `hub`다. 레포는 bench 기록의 워크트리에서 찾고, 기록이 없는 작업대 워크트리는 그 폴더의 `.git` 파일에서 찾는다. 기록에 cwd가 없으면 `null`이고 트리는 아무것도 보이지 않는다. 시험은 `tests/test_folder_name.py`다.

트리 mod는 세션 이름 바로 뒤, 같은 줄(30px)에 폴더 이름을 흐린 11px 글자로 보인다(`folderTag`). 폴더 칸은 이름이 남긴 자리만 쓰므로(flex_1, 기준 폭 0) 줄이 모자라면 폴더가 먼저 잘리고 이름은 그대로 남는다. 하위 줄의 이름 칸은 원래 flex_1이라 먼저 줄어들었으므로 제 폭을 쓰게 바꿨다. 생성기는 `build_tree_superset.py`, 원본은 `upstream/agents-0.1.15.js`이고, 시험은 `tests/test_tree_folder.mjs`다(인자로 다른 main.js를 주면 그 판을 시험한다).

설치는 운영자 화면을 바꾸므로 시각을 맞춘 뒤에 한다. Herdr는 main.js가 바뀌면 mod를 제자리에서 다시 읽는다.

```sh
cp ~/.config/herdr-app/mods/workbench-tree-next/main.js <백업 경로>/workbench-tree-next.main.js.bak
cp mods/workbench-tree-next/main.js ~/.config/herdr-app/mods/workbench-tree-next/main.js
herdr-app check ~/.config/herdr-app/mods/workbench-tree-next
herdr-app shot <파일.png>
```

되돌릴 때는 백업을 같은 자리에 다시 복사한다.

## 끊긴 세션 이어받기 (takeover, B1 2026-11-11)

`takeover <끊긴 주소> [--resume <Claude 세션 id>] [--model …] [--fresh --task …] [--dry-run]`은 터미널이 끝난 세션을 새 터미널로 다시 열고 트리 자리를 그대로 넘긴다. `hc get`이 live이면 거절하고, finished이거나 hc가 모르는 주소면 진행한다. 새 주소(hc가 준 값, 새 터미널의 HC_TERMINAL_ID)가 부모 자리·자식·자식 워크트리의 close 권한·안 읽은 보고를 넘겨받고, 옛 기록은 `replaced`로 닫힌다. 실행 전마다 `state.json`·`view.json`을 `mailbox/backups/`에 복사하고 되돌리는 `cp` 명령을 출력한다. 디렉터는 아무 터미널에서, 그 아래는 등록된 부모만 이어받는다. Codex는 `--fresh --task`로만 새 대화를 연다. `hc kill`로 부모를 끝내면 자식 터미널도 끝나므로 위에서부터 하나씩 이어받는다. 이어받은 부모 아래 살아 있는 자식은 hc가 아는 부모가 옛 주소로 남아 트리에서 떨어져 보일 수 있다.


## 보존 및 재시도 제한

Git의 `assume-unchanged`·`skip-worktree`가 켜진 추적 파일은 status가 변경을 숨길 수 있다. 플래그가 있는 워크트리는 자동 정리하지 않는다. origin의 모든 브랜치 참조를 fetch·prune한 뒤 미push 여부를 판단하므로 원격에서 삭제된 브랜치의 낡은 추적 참조를 근거로 정리하지 않는다.

spawn 증거의 `launch_attempted=false`는 hc 실행 전 준비 실패다. 남은 워크트리를 보존하며 별개의 새 세션은 만들 수 있다. 같은 브랜치를 재사용해 소유권을 인수하지 않는다. `launch_attempted=true`인데 결과가 불명확하면 새 실행을 막는다. 증거의 argv·시각과 실제 hc terminal을 대조하고, 확인된 세션을 먼저 복구·정리한다. 자동 복구 명령은 첫 판에 없다. 상태 파일을 임의로 지워 재시도하지 않는다.

hc 실행 전에 실패한 spawn(`launch_attempted=false`, 예: 스킬 링크 시간 초과)은 세션이 없으므로 같은 부모가 `discard <워크트리 경로>`로 치운다. 규칙은 `close`와 같다. 변경·무시된 사용자 파일·미push 커밋이 있으면 보존하고, origin/main에 머지된 브랜치만 `git branch -d`로 지운다. 결과는 그 spawn 증거의 `discard_result`(실패 시 `discard_attempts`)에 남는다. 스킬 링크 시간 한도는 11/10 사례(B11) 뒤 30초에서 120초로 늘렸다.

워크트리 생성 뒤 hc가 실행을 거절하면 등록된 노드가 없어 `close`로 정리할 수 없다. 같은 브랜치 재시도는 보존된 워크트리와 실패 증거 경로를 알리고 멈춘다. 파일·브랜치·기록을 바꾸거나 hc를 다시 실행하지 않는다. 운영자가 증거와 실제 터미널을 확인해 복구 방법을 정해야 한다.

## 실사용 설정과 리허설

활성 설정 `bench.yaml`은 실사용 hub 값으로 복원했다. 실사용 보관본은 `bench.production.yaml`, 리허설 설정 보관본은 `bench.rehearsal.yaml`이다. 리허설 수신함은 `fixture/mailbox`에 분리 보존한다. 복원 근거는 `acceptance.md`에 있다. 트리 mod는 동시에 활성 작업대 스페이스 1개의 계층·점만 처리한다.
