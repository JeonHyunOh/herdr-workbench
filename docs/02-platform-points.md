# 02. 맥·리눅스 전제 지점 목록

작업대 도구는 macOS에서 만들고 시험했다. 이 문서는 macOS·리눅스를 전제로 한 코드 지점을 모두 적는다. 윈도우에서 직접 돌리려면(갈래 2, `prompts/`) 아래 지점을 모두 옮겨야 한다. WSL2 우분투에서 돌리면(갈래 1, `wsl2/`) bench 지점은 대부분 그대로 돌고, mod 지점만 남는다.

행 번호는 이 묶음의 `reference/` 사본 기준이다. 원본이 바뀌면 행이 달라질 수 있으니 함수 이름과 코드 조각으로 찾는다.

## 1. bench 세션 도구 (`reference/workbench/`)

| # | 위치 | 하는 일 | 윈도우에서 깨지는 것 | 바꿀 방향 | WSL2 우분투 |
|---|---|---|---|---|---|
| B1 | `bench.py` 6행 `import fcntl`, 466행 `fcntl.flock(lock, fcntl.LOCK_EX)` | 수신함(`state.json`)을 쓰기 전에 배타 잠금을 잡는다. 여러 세션이 동시에 보고해도 기록이 섞이지 않는다 | 윈도우 Python에는 `fcntl`이 없다. import에서 바로 멈춘다 | 윈도우에서는 `msvcrt.locking`이나 잠금 파일을 쓰는 잠금으로 바꾼다. 잠금 범위와 해제 시점은 그대로 둔다 | 그대로 돈다 |
| B2 | `bench.py` 391행 `process_metadata()`의 `/bin/ps -o pid=,ppid=,lstart=,comm=` | 프로세스의 부모·시작 시각·실행 파일을 읽어 Codex 작업자의 MCP 호출이 정말 그 터미널의 Codex에서 왔는지 대조한다(1642행 비교) | `/bin/ps`가 없다 | 윈도우 프로세스 조회(예: PowerShell `Get-CimInstance Win32_Process`의 ParentProcessId·CreationDate·ExecutablePath)로 같은 4개 값을 만든다 | 고쳤다(원본 커밋 0684dd5). 리눅스 `ps`의 `comm`은 실행 파일 이름만 준다(컨테이너 실측 `'python3'`). 그래서 리눅스에서는 `/proc/<pid>/exe`로 전체 경로를 읽는다(382행 `proc_executable()`). 우분투 24.04 컨테이너에서 `tests/test_process_linux.py` 7개가 통과했다. 이 대조는 Codex MCP가 `HC_TERMINAL_ID`를 받지 못했을 때만 쓰는 대체 경로이고, bench는 평소 그 값을 MCP에 넘긴다(596행 `env_vars`) |
| B3 | `bench.py` 588행 `'/usr/bin/env', '-u', 'ANTHROPIC_API_KEY', '-u', 'OPENAI_API_KEY', 'TERM=xterm-256color'` | 자식 세션 환경에서 API 키 2개를 지우고 띄운다. 구독 로그인만 쓰게 하는 장치다 | `/usr/bin/env`가 없다 | 키 제거를 `native_exec.py` 안에서 한다(이미 그 안에서 한 번 더 지우고 확인한다). argv 앞의 `env` 단계는 뺀다. 키 제거 자체는 빼지 않는다 | 그대로 돈다 |
| B4 | `bench.py` 589·595행 `'python3'` | 자식 실행 감싸기와 Codex 보고용 MCP 서버를 `python3`로 띄운다 | 윈도우 Python은 보통 `py` 또는 `python`이다 | 설정(`bench.yaml`)에 파이썬 실행 파일 경로 키를 두고 그 값을 쓴다 | 그대로 돈다 |
| B5 | `native_exec.py` 79행 `os.execve(argv[0], argv, child_env)`, `bench.py` 1215행 `os.execv` | 감싸기 프로세스가 자기 자리를 진짜 CLI(Claude Code·Codex)로 바꾼다. 터미널의 프로세스가 곧 CLI가 된다 | 윈도우의 `exec`는 새 프로세스를 띄우고 원래 프로세스를 끝낸다. 터미널(herdr-core)은 프로그램이 끝났다고 본다 | `subprocess`로 자식을 띄우고 끝날 때까지 기다린 뒤 종료코드를 그대로 돌려준다. 표준 입출력은 넘기지 않고 상속한다 | 그대로 돈다 |
| B6 | `native_exec.py` 64~66행, `bench.py` 419~421행 `os.open(directory, os.O_RDONLY)` + `os.fsync` | JSON을 임시 파일에 쓰고 바꿔 끼운 뒤 폴더까지 디스크에 내린다 | 윈도우에서는 폴더를 이 방식으로 열 수 없다(권한 오류) | 윈도우에서는 폴더 fsync를 건너뛴다. 파일 fsync와 `os.replace`는 그대로 둔다 | 그대로 돈다 |
| B7 | `bench.py` 185행 `checked_state_file()`의 `path.startswith('/')` | Codex 세션 상태 파일이 절대 경로인지 확인한다 | `C:\...` 경로를 절대 경로로 보지 않아 거절한다 | `Path(path).is_absolute()`로 바꾼다 | 그대로 돈다 |
| B8 | `bench.py` 178행 `SHELLS` | 재부팅 뒤 터미널에 셸만 남았는지 판단한다(`recover`) | `pwsh`·`powershell`·`cmd`가 목록에 없다 | 윈도우 셸 이름(확장자 `.exe` 포함)을 더한다 | 그대로 돈다 |
| B9 | `bench.py` 1250행 `exec python3 … relaunch` | 되살아난 셸에 이 한 줄을 넣어 같은 세션을 다시 띄운다 | PowerShell에는 `exec`가 없다 | PowerShell용 한 줄을 따로 만든다. 셸 종류는 B8 판단 결과로 고른다 | 그대로 돈다 |
| B10 | `bench.py` 760행 `['bash', self.config['link_repo_skills'], …]` + `reference/harness/link-repo-skills.sh` | 작업자 워크트리를 만든 뒤 레포의 `.claude/skills/<이름>`을 `.agents/skills/<이름>`으로 링크해 Codex도 팀 스킬을 읽게 한다 | `bash`가 없을 수 있다(Git for Windows가 있으면 Git Bash가 있다). `ln -s`는 개발자 모드나 관리자 권한이 없으면 실패한다 | Python으로 옮기거나, 링크 대신 폴더 접합(junction)을 쓴다. 레포에 `.claude/skills`가 없으면 아무것도 하지 않고 끝나는 동작은 그대로 둔다 | 그대로 돈다 |
| B11 | `bench.py` 204행 `claude_project_dir()` | Claude Code 대화 기록 폴더(`~/.claude/projects/<폴더 이름을 바꾼 값>`)를 찾아 세션 id·현재 모델을 읽는다 | 윈도우 경로(`C:\Users\…`)를 바꾼 이름이 같은 규칙인지 확인되지 않았다 | 받는 사람 PC의 `~/.claude/projects/` 폴더 이름을 보고 규칙을 맞춘다 | 그대로 돈다(리눅스 경로) |
| B12 | `bench.py` 322행 `gitdir:` 정규식 | 워크트리의 `.git` 파일에서 원래 레포를 찾아 트리에 레포 이름을 보인다 | Git for Windows가 쓰는 경로 모양(`C:/…`)에서 맞는지 확인되지 않았다 | 시험을 하나 더해 확인한다 | 그대로 돈다 |
| B13 | `bench.yaml`의 `vendors.codex.process_executable` | B2 대조에 쓰는 Codex 실제 실행 파일 경로. npm 전역 설치에서 `codex` 명령은 node 스크립트이고, 실제 실행 파일은 그 아래 플랫폼 패키지에 있다 | 윈도우는 플랫폼 패키지 이름과 실행 파일 이름(`.exe`)이 다르다 | 받는 사람 PC에서 실제 경로를 찾아 넣는다 | 우분투의 실제 경로를 찾아 넣는다 |
| B14 | `bench.py` 1571행 `herdr_app … tab.rename` | 새 세션 탭 이름을 표시 이름으로 바꾼다. `bench.yaml`에 `herdr_app`이 없으면 꺼진다 | 윈도우 Herdr 앱 명령 이름·위치가 다를 수 있다(확인 안 됨) | 받는 사람 PC에서 경로를 찾아 넣거나 비워 둔다 | WSL 안에는 Herdr 앱이 없다. 비워 둔다 |
| B15 | `bench.py` 593~594행 Codex `--sandbox workspace-write`·`--ask-for-approval on-request` | Codex 작업자를 쓰기 가능한 샌드박스로 띄우고, 밖으로 나가는 명령은 승인 요청으로 돌린다 | 윈도우 Codex 샌드박스는 맥·리눅스와 동작이 다르다(확인 안 됨) | 첫 리허설에서 작업자가 워크트리 안 파일 쓰기·시험·커밋을 승인 없이 할 수 있는지 본다 | 리눅스 샌드박스로 돈다 |
| B16 | `bench.py` 28행 `KST = ZoneInfo('Asia/Seoul')` | 날짜·요일 검사와 보고 시각을 한국 시간으로 계산한다 | 윈도우 Python에는 시간대 데이터가 없다. tzdata 패키지가 없으면 import에서 멈춘다 | `pip install tzdata`. 코드는 그대로 둔다 | 우분투는 tzdata 패키지가 있으면 된다 |

## 2. Herdr mod (`reference/workbench/build_*.py`, `reference/mods/`)

트리·Files·메뉴 mod는 Herdr에 들어 있는 기본 mod(`agents`·`files`·`menu`)를 `herdr-app do mod.clone`으로 복제한 뒤 생성기가 정해진 위치를 고쳐 만든다. 생성기는 고칠 위치가 정확히 1번씩 나와야 진행하고, Herdr 판이 달라 위치가 바뀌었으면 멈춘다. 받는 사람 Herdr 판이 다르면 이 단계에서 멈출 수 있다. 시험한 판은 Herdr App 0.1.15, herdr-core 0.1.20이다.

| # | 위치 | 하는 일 | 깨지는 것 | 바꿀 방향 |
|---|---|---|---|---|
| M1 | `build_tree_superset.py` 63행 `exec("python3", [BENCH_HELPER, …, "tree-refresh"])`, 90·94행 `readTextFile(BENCH_CONFIG)`·`tree.json` | 트리가 30초마다 bench에 `tree-refresh`를 부르고, bench가 쓴 `tree.json`을 읽어 계층·역할·모델·안 읽은 보고 수를 그린다 | 윈도우 네이티브: `python3` 이름. WSL2: mod는 윈도우 앱 안에서 돌고 bench 파일은 WSL 안에 있다 | 네이티브는 파이썬 실행 파일을 설정값으로. WSL2는 `exec`·`readTextFile`에 `{ on: <머신 이름> }`을 준다(Herdr mod API가 지원한다) |
| M2 | 트리의 주소·스페이스 대조 | bench 기록의 주소(`t7`)와 Herdr가 보여 주는 터미널을 맞춘다 | WSL2: 앱은 다른 머신의 주소와 스페이스 id에 `<머신>/` 접두를 붙인다(예 `wsl/t7`) | 대조 전에 접두를 맞춘다 |
| M3 | `build_wb_files.py` 83행 `{ on: absolute ? null : on }`, `exec("open", …)` | Files 패널이 md를 렌더링하고, 절대 경로 파일을 이 컴퓨터에서 연다 | WSL2: 절대 경로를 윈도우 쪽에서 찾는다. `open`은 macOS 명령이다 | 스페이스의 머신에서 읽게 한다. 열기 명령을 OS별로 고른다 |
| M4 | `build_wb_menu.py` 15행 `HUB = '/home/you/Project/work/hub'`, 43행 `exec("sh", …)` + `find` | 터미널 우클릭 메뉴에 그 터미널이 최근 쓴 파일 이름을 'Files에서 열기'로 보인다 | 허브 경로가 고정이다. 윈도우 네이티브에는 `sh`·`find`가 없을 수 있다 | 허브 경로를 생성기 인자로. 네이티브는 PowerShell 판, WSL2는 `{ on: <머신> }` |
| M5 | `mods/wb-md/main.js` 56행 `exec("open", ["-R", this.file])` | md 뷰어의 'Finder' 단추 | macOS 전용 | OS별로 고르거나 단추를 숨긴다 |
| M6 | `mods/wb-prs/main.js` 8행 `ORG = "YOUR_ORG"` | '내 PR' 패널. `gh` 로그인으로 그 조직의 내 PR·내 검토 PR을 3분마다 가져온다 | 조직 이름을 받는 사람이 채워야 한다. `gh`가 어느 쪽(윈도우·WSL)에 로그인돼 있는지에 따라 `on`이 달라진다 | 조직 이름을 채운다. 필요 없으면 레이아웃에서 이 패널을 뺀다 |

## 3. 확인하지 못한 것

- 윈도우 실기에서는 아무것도 돌려 보지 않았다. 위 표의 '깨지는 것'은 코드와 공식 문서를 읽고 판단한 것이다.
- 우분투 24.04 컨테이너(aarch64, Python 3.12.3, git 2.43.0, git 기본 브랜치 설정 없음)에서 `wsl2/setup.py`로 설치하고 시험 174개를 돌려 모두 통과했다(원본 커밋 0684dd5 기준). 예전에는 시험 1개가 git 기본 브랜치 설정에 기댔는데, 원본 커밋 88ea179에서 시험이 임시 원격을 `-b main`으로 만들게 고쳐 이제 기대지 않는다. 받는 사람 PC의 WSL은 x86_64라 아키텍처가 다르다.
- 윈도우판 herdr-core의 `hc run` 동작(PTY, 라벨, 부모 기록)이 맥과 같은지는 확인하지 않았다.

## 4. 묶음을 만들 때 바꾼 이름

`reference/` 사본은 작성자 작업대에서 떴고, 개인·팀 이름을 아래처럼 바꿨다. 코드 동작은 바꾸지 않았다. 시험 2개 경로는 묶음 폴더 모양에 맞게 바꿨다.

| 원래 | 바꾼 값 |
|---|---|
| 작성자 홈 경로 | `/home/you` |
| 작성자 이름·계정 | `운영자`, `your-account` |
| 세션 별명 | `Director`, `디렉터`, `내탭` |
| 허브 폴더 이름 | `hub` |
| 조직 이름 | `YOUR_ORG` |
| 제품·기획 레포 이름 | `team-repo`, `planning-repo` |
| 시험의 정책·역할 경로 | `reference/policy.example.yaml`, `reference/roles/` |

## 5. 라이선스

Herdr App·herdr-core·Herdr TUI는 Apache License 2.0이다(GitHub 레포 `herdrdev/herdr-app`·`herdrdev/herdr-core`·`herdrdev/herdr`). 생성기 3개(`build_tree_superset.py`·`build_wb_files.py`·`build_wb_menu.py`)에는 Herdr 기본 mod의 코드 조각이 '찾을 위치'와 '바꿀 내용'으로 들어 있고, `mods/workbench-next-layout.json`은 Herdr 기본 레이아웃 `main`을 복제해 고친 것이다. 라이선스 전문은 `reference/LICENSES/Herdr-Apache-2.0.txt`에 있다. 이 파일들은 Herdr 원본을 고친 것이다.
