# Claude Code로 작업대 세팅하기

이 파일 하나로 작업대를 세팅한다. Herdr를 설치한 뒤 Herdr 터미널에서 Claude Code를 열고, 아래 프롬프트를 S0부터 차례로 붙여 넣는다. Claude가 단계마다 확인하고 결과를 보여 준다. 사람의 설정을 바꾸는 명령은 사람이 직접 실행한다.

작업대는 Herdr 위에서 Claude Code와 Codex 세션을 디렉터 → 리드 → 작업자 계층으로 열고, 보고를 수신함으로 모으는 환경이다. 계층마다 맡는 일과 규칙은 [세션 계층 체계도](docs/04-session-hierarchy.md)에 있다. 세팅이 끝나면 다음이 생긴다.

- **bench**: 세션을 열고(spawn) 지시·보고·정리(close)하는 명령 도구
- **역할 지시문 5개**: 디렉터, 리드, 코딩 작업자, 검토 작업자, 조사 작업자
- **정책 파일**: 에이전트가 사람 승인 없이 해도 되는 일과 승인이 필요한 일의 경계
- **Herdr 화면**: 세션 트리(계층·역할·모델·안 읽은 보고 수), md를 렌더링하는 Files 패널, 터미널 우클릭 'Files에서 열기', md 뷰어, 내 PR 패널

## 운영체제별 상태

| 항목 | macOS | 윈도우 + WSL2 | 윈도우 직접 |
|---|---|---|---|
| bench·역할·정책 | 원본 환경이다. 시험 174개 통과 | 우분투 24.04 컨테이너에서 설치와 시험 174개 통과 | 이식이 필요하다(docs/02 B1~B16). 해 본 적 없음 |
| 트리·Files·메뉴·md 뷰어·PR 패널 | 생성기가 Herdr 0.1.15 기본 mod에 그대로 적용되고 `herdr-app check`를 통과한다 | 보류(wsl2/known-gaps.md G1~G6). Herdr 기본 Agents 패널로 대신한다 | 이식이 필요하다(docs/02 M1~M6). 해 본 적 없음 |

새 PC에서 처음부터 끝까지 따라 해 본 적은 아직 없다. 막히면 Claude가 멈추고 그 단계의 출력을 남긴다.

## 시작 전에 사람이 할 것

1. Herdr 앱과 herdr-core(`hc`)를 설치한다. 윈도우 + WSL2라면 [wsl2/README.md](wsl2/README.md) 1~3절을 먼저 따른다.
2. Claude Code와 Codex를 설치하고 각자 구독 계정으로 로그인한다. API 키로 로그인하지 않는다.
3. git과 Python 3.9 이상을 준비한다. PR 패널을 쓰려면 `gh`에 로그인한다.
4. 이 레포를 받는다: `git clone <받은 레포 주소> herdr-workbench`. 이 파일만 받았다면 보낸 사람에게 레포 주소와 접근 권한을 받는다.
5. Herdr에서 터미널을 열고 레포 폴더로 가서 `claude`를 실행한다. 윈도우 + WSL2라면 WSL 머신의 터미널에서 연다. S0~S6은 이 세션 하나에서 이어 간다.

Claude Code 입력창에서 `!` 뒤에 명령을 쓰면 사람이 그 명령을 실행하고 출력이 대화에 남는다. 아래에서 "사람이 실행한다"는 이 방법을 말한다.

## 모든 단계에 적용하는 규칙

[docs/03-safety-rules.md](docs/03-safety-rules.md)가 정본이다. 요약하면 이렇다.

- 로그인 정보·API 키·토큰을 읽거나 복사하거나 출력하지 않는다.
- 승인 창과 trust 질문에는 사람이 답한다. 권한 검사를 건너뛰는 옵션을 쓰지 않는다.
- `~/.claude`, Codex 설정, 셸 프로필, Herdr 설정을 바꾸는 명령은 대상 경로와 내용을 먼저 보여 주고 사람이 실행한다.
- `HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`을 바꾸지 않는다.

진행 기록은 레포 폴더의 `setup-notes.md`에 남긴다. 세션이 끊겨도 맨 아래 '끊겼을 때 이어 하기'로 다시 시작한다.

## S0. 맥락과 경로 정하기

```text
이 폴더는 Herdr 작업대 세팅 묶음이다. SETUP-WITH-CLAUDE.md를 처음부터 끝까지 읽고, 그 '모든 단계에 적용하는 규칙'과 docs/03-safety-rules.md를 이 세션 내내 지킨다. README.md, docs/01-what-is-this.md, docs/02-platform-points.md, docs/04-session-hierarchy.md도 읽는다. 이 단계에서는 파일과 설정을 바꾸지 않고 읽기 명령만 쓴다.

이 컴퓨터가 macOS, 윈도우 + WSL2(지금 WSL 안에서 돌고 있음), 윈도우 직접(PowerShell) 중 어느 것인지 확인한다. 경로를 하나 고르고 그 경로에서 S1~S6이 무엇을 하는지 5줄 이내로 요약한다. 그 경로의 '운영체제별 상태'에서 확인되지 않은 부분도 말한다. 레포 폴더에 setup-notes.md를 만들고 고른 경로와 확인한 근거를 적는다. 이미 있으면 덮어쓰지 말고 먼저 읽어서 보여 준다.
```

**확인할 것**: 고른 경로가 맞는지, setup-notes.md가 생겼는지 본다.

## S1. 설치 확인

```text
읽기 전용으로 설치 상태를 확인한다. herdr-app, hc, claude, codex, Python(python3, python, py -3 중 되는 것), git, gh의 실행 파일 경로와 버전을 표로 정리한다. 로그인 정보와 환경변수의 비밀값은 읽지 않는다. 구독 로그인 상태는 사람이 각 화면에서 확인하도록 안내한다.

Python에서 `import yaml`과 `from zoneinfo import ZoneInfo; ZoneInfo('Asia/Seoul')`이 되는지 본다. 안 되면 이 Python이 어디서 설치됐는지 확인하고 PyYAML·tzdata 설치 명령을 보여 준다. 사람이 실행한 뒤 다시 확인한다.

Herdr 스페이스 id를 확인한다. macOS는 `herdr-app status`의 space 값이다. 다른 경로는 `herdr-app --help`와 `herdr-app commands`에서 방법을 찾고, 못 찾으면 '확인 필요'로 남긴다. 앞에 `<머신>/` 접두가 붙어 있으면 뗀 값을 쓴다. Herdr 설정 폴더 위치도 `herdr-app --help`의 Home 줄에서 확인한다.

사람에게 Claude와 Codex에서 쓸 기본 모델 이름을 묻는다(예: claude-opus-5-5, gpt-6.1-sol). 결과 표와 스페이스 id, 설정 폴더, 모델 이름을 setup-notes.md에 적는다.
```

**확인할 것**: 빠진 도구가 없는지, 스페이스 id가 '확인 필요'로 남지 않았는지 본다.

## S2. bench 설치

macOS와 윈도우 + WSL2는 A를, 윈도우 직접은 B를 붙여 넣는다.

### A. macOS·WSL2·리눅스

```text
setup-notes.md를 읽는다. 사람에게 2가지를 묻는다. 작업대를 설치할 새 폴더(예: ~/workbench, 아직 없는 폴더여야 한다)와 디렉터가 일할 폴더(평소 레포들을 두는 곳, 예: ~/work)다.

다음 미리보기를 실행한다. macOS면 `--herdr-app <herdr-app 실제 경로>`를 붙인다(새 세션의 탭 이름 기능에 쓴다). WSL2에서는 붙이지 않는다.

python3 wsl2/setup.py --target <설치 폴더> --hub <디렉터 폴더> --space-id <스페이스 id> --claude-model <Claude 모델> --codex-model <Codex 모델>

출력의 도구 경로, 만들 파일, bench.yaml 전체 내용, '먼저 고칠 것'을 사람에게 설명한다. '<채울 것'으로 남은 값이 있으면 이유를 찾아 --hc, --claude, --codex, --codex-process로 넣고 미리보기를 다시 돌린다. 이 명령은 새 설치 폴더에만 쓰고 ~/.claude, ~/.codex, 셸 프로필, Herdr 설정은 읽지도 바꾸지도 않는다.

사람이 미리보기를 확인했다고 답하면 같은 명령에 --apply를 붙여 실행한다. 끝에 나오는 시험 결과(통과·실패·건너뜀)를 그대로 보고한다. 실패를 통과로 취급하지 않는다. 설치 폴더의 절대 경로를 INSTALL로 setup-notes.md에 적는다.
```

### B. 윈도우 직접

```text
setup-notes.md를 읽는다. 레포 폴더 아래 port/를 새로 만들고(이미 있으면 멈추고 묻는다) reference/ 전체를 그 안에 복사한다. port/의 절대 경로를 INSTALL로 setup-notes.md에 적는다. workbench/만 따로 떼지 않는다. 시험이 형제 폴더 roles/, harness/와 policy.example.yaml을 찾는다.

INSTALL/workbench에서 `<Python> -m unittest discover -s tests -p "test_*.py"`를 실행해 고치기 전 결과로 남긴다. 시험은 hc·claude·codex를 실제로 부르지 않는다.

docs/02-platform-points.md 1절의 B1~B16을 하나씩 확인하고 INSTALL 사본을 윈도우에 맞게 고친다. 항목마다 그 동작을 확인하는 시험을 1개 이상 더한다. B1 수신함 잠금과 B3 자식 환경의 API 키 2개 제거는 반드시 유지한다. 키 값은 읽지 않는다. 확인할 수 없는 동작은 추측하지 말고 '확인 필요'와 이유를 남긴다. 고친 뒤 같은 시험을 다시 돌리고, B1~B16별 변경과 시험 결과, B4에서 정한 Python 실행 파일 설정 키 이름을 setup-notes.md에 적는다.

그다음 INSTALL/workbench/bench.yaml 초안을 JSON 문법으로 만든다. 키는 wsl2/setup.py의 config 사전과 같다: space_id, space_name, mailbox(INSTALL/mailbox), roles(INSTALL/roles), cwd(디렉터가 일할 폴더, 사람에게 묻는다), worktrees(INSTALL/worktrees), hc, link_repo_skills, policy(INSTALL/policy.yaml, policy.example.yaml 사본), vendors.claude.executable·model, vendors.codex.executable·model·process_executable(B13: 명령 래퍼가 아닌 실제 실행 파일), B4의 Python 키. 전체 내용을 보여 주고 사람이 확인한 뒤에만 저장한다. mailbox/, worktrees/ 폴더와 policy.yaml 사본도 만든다.
```

**확인할 것**: 시험 결과와 bench.yaml 내용을 본다. 다음 단계로 가는 기준은 실패 0이거나, 남은 실패마다 사람이 받아들인 이유가 setup-notes.md에 적혀 있는 것이다.

## S3. 역할 지시문과 정책

```text
setup-notes.md를 읽는다. INSTALL/roles/에 secretary.md(디렉터), lead.md, worker-code.md, worker-review.md, worker-query.md가 있는지 확인한다. 5개 파일의 `<정책 파일 경로>`를 bench.yaml의 policy 값으로 바꾼다. 명령 예시 안의 `<모델명>`, `<작업 지시>` 같은 다른 `<…>`는 에이전트가 쓸 때 채우는 입력칸이라 그대로 둔다.

INSTALL/policy.yaml을 읽고, 에이전트가 승인 없이 하는 일과 승인 뒤에 하는 일, 하지 않는 일을 사람에게 표로 요약해 보여 준다. 이 사람의 팀 규칙에 맞게 고칠 곳이 있는지 묻고, 답에 따라 고친다. 바꾼 내용을 setup-notes.md에 적는다.
```

**확인할 것**: 남은 `<정책 파일 경로>`가 없는지, 정책 요약이 내 일의 경계와 맞는지 본다.

## S4. Herdr 화면 (트리·Files·메뉴·md 뷰어·PR 패널)

윈도우 + WSL2는 이 단계를 건너뛴다. 트리 mod가 WSL 안의 bench 기록을 읽는 변경이 아직 없어서다(wsl2/known-gaps.md). 그동안은 Herdr 기본 Agents 패널과 `bench ls`를 쓴다.

```text
setup-notes.md를 읽는다. INSTALL/workbench/README.md의 'Herdr 업데이트 뒤 트리 재생성'과 docs/02-platform-points.md 2절(M1~M6)을 읽는다. `herdr-app commands`에서 mod.clone, layout.switch의 인자를 확인한다.

만들 것은 다음과 같다. 이름이 Herdr 설정 폴더(S1에서 확인)의 mods/, layouts/에 이미 있으면 멈추고 묻는다. 기존 mod와 레이아웃은 덮어쓰지 않는다.
- workbench-tree-next: 기본 agents를 `herdr-app do mod.clone '{"name":"agents","as":"workbench-tree-next"}'`로 복제한다. 복제본의 main.js를 INSTALL 아래 임시 파일로 복사하고, `python3 INSTALL/workbench/build_tree_superset.py --source <임시 파일> --output <설정 폴더>/mods/workbench-tree-next/main.js --config INSTALL/workbench/bench.yaml`을 실행한다.
- wb-files: 기본 files를 같은 방법으로 wb-files로 복제한 뒤 `python3 INSTALL/workbench/build_wb_files.py <설정 폴더>/mods/wb-files/main.js`
- wb-menu: 먼저 INSTALL/workbench/build_wb_menu.py의 HUB 값을 bench.yaml의 cwd로 바꾼다. 기본 menu를 wb-menu로 복제한 뒤 `python3 INSTALL/workbench/build_wb_menu.py <설정 폴더>/mods/wb-menu/main.js`
- wb-md: INSTALL/mods/wb-md 폴더를 <설정 폴더>/mods/wb-md로 복사한다.
- wb-prs: 사람에게 PR을 볼 GitHub 조직 이름을 묻는다. 있으면 INSTALL/mods/wb-prs/main.js의 ORG 값을 바꾸고 <설정 폴더>/mods/wb-prs로 복사한다. 없으면 이 패널을 만들지 않고 레이아웃 사본에서 wb-prs 블록을 뺀다.
- 레이아웃 workbench: INSTALL/mods/workbench-next-layout.json을 <설정 폴더>/layouts/workbench.json으로 복사한다.

복제는 반드시 mod.clone으로 한다. mod.clone이 mod 안의 자기 이름 참조를 새 이름으로 바꿔 주기 때문에, 폴더를 그냥 복사하면 트리의 정렬 메뉴와 Files의 아이콘 경로가 틀어진다. 생성기는 기준 코드의 변경 위치가 정확히 1개씩 맞을 때만 쓴다. 위치가 맞지 않는다고 멈추면 Herdr 버전이 달라서다. 억지로 고치지 말고 그 출력과 `herdr-app --version`을 남기고 멈춘다.

윈도우 직접이면 M1(python3 이름), M3·M5(macOS `open`), M4(`sh`·`find`)를 윈도우에 맞게 바꾼 판을 INSTALL 아래에 만든다. 경로 구분자와 드라이브 문자도 확인한다. 바꾼 곳과 확인하지 못한 곳을 setup-notes.md에 적는다.

위 명령을 순서대로 담은 스크립트 1개를 INSTALL/apply-mods.sh(윈도우는 apply-mods.ps1)로 쓰고 전체를 보여 준다. 실행은 사람이 한다. 스크립트 끝에서 만든 mod 폴더마다 `herdr-app check <폴더>`를 실행한다. 레이아웃 전환(`herdr-app do layout.switch '{"name":"workbench"}'`)과 되돌리기(`'{"name":"main"}'`)는 스크립트에 넣지 말고 따로 안내한다.
```

**확인할 것**: `herdr-app check`가 5개 mod 모두 통과하는지 본다. 레이아웃을 바꾸고 왼쪽에 트리와 PR 패널, 오른쪽에 Files가 보이는지 본다. 트리의 역할·모델 표시는 S5에서 세션을 연 뒤에 나온다.

## S5. 리허설

```text
setup-notes.md를 읽는다. 실제 업무 자료가 없는 연습용 폴더를 사람에게 경로를 보여 준 뒤 만든다. 그 안에 연습 레포를 git init -b main으로 만들고, 같은 폴더의 bare 레포를 origin으로 붙여 첫 커밋을 push한다. close는 매번 origin/main을 fetch해 머지 여부를 보기 때문에 origin이 필요하다. 외부 원격과 기존 레포는 건드리지 않는다.

사람에게 디렉터를 여는 명령을 보여 준다. 사람이 실행한다.
python3 INSTALL/workbench/bench.py --config INSTALL/workbench/bench.yaml spawn --role secretary --vendor claude --model <Claude 모델> --cwd <연습 폴더> --display 디렉터
(INSTALL은 실제 절대 경로로, 윈도우 직접이면 B4에서 정한 Python 이름으로 바꾼다)

새 터미널에 디렉터가 뜨면 사람이 trust 질문에 답하고, 디렉터에게 이렇게 맡긴다: "연습 레포에 README 한 줄을 고치는 일을 리드에게 맡겨라. 리드는 코딩 작업자 1개를 워크트리로 열어 브랜치에서 커밋하게 하고, 보고를 받아 close까지 해라."

그동안 이 세션은 `python3 INSTALL/workbench/bench.py --config INSTALL/workbench/bench.yaml ls`로 상태만 읽는다. 다음을 확인해 setup-notes.md에 적는다. 디렉터 → 리드 → 작업자 계층이 트리와 ls에 보이는지, 작업자 보고가 리드에게, 리드 보고가 디렉터에게 도착하는지, close가 세션을 정리하는지. 작업자 브랜치는 origin/main에 머지되지 않았으므로 close가 워크트리를 보존하고 이유를 말하는 것이 정상이다. Codex 작업자를 썼다면 워크트리 안에서 파일 쓰기·시험·커밋이 승인 없이 되는지도 적는다. 승인 창에는 사람이 답한다.
```

**확인할 것**: 보고 2개가 제자리에 도착했는지, close 결과가 위 설명과 같은지 본다.

## S6. 세팅 뒤 매일 쓰는 법

```text
setup-notes.md를 읽고, 이 사람이 매일 쓸 명령을 INSTALL/DAILY.md로 정리해 보여 준다. 다음을 넣는다.
- 디렉터 열기: S5의 spawn 명령에서 --cwd를 bench.yaml의 cwd(디렉터가 일할 폴더)로 바꾼 것
- 세션 목록과 수신함: bench ls, bench inbox
- 컴퓨터를 다시 켠 뒤: bench recover --dry-run으로 미리 보고, 문제가 없으면 --dry-run을 빼고 실행
- Herdr를 업데이트한 뒤: S4를 새 mod 이름으로 다시 하고, 확인한 뒤 레이아웃을 바꾼다
- 더 자세한 설명: INSTALL/workbench/README.md
연습 폴더를 지울지는 사람에게 묻는다. 지운다면 경로를 보여 주고 사람이 지운다.
```

## 끊겼을 때 이어 하기

```text
SETUP-WITH-CLAUDE.md의 '모든 단계에 적용하는 규칙'과 docs/03-safety-rules.md를 지킨다. setup-notes.md를 읽고 끝난 단계와 남은 단계를 보여 준다. 마지막으로 끝난 단계의 결과가 실제 파일과 맞는지 확인한 뒤, 사람이 고른 단계부터 SETUP-WITH-CLAUDE.md의 프롬프트를 따라 이어 간다.
```

## 이 묶음에 없는 것

보낸 사람의 개인 설정(`~/.claude`의 CLAUDE.md·스킬·훅, Codex 설정), 로그인 정보, 수신함과 세션 기록, 회사 레포 내용은 넣지 않았다. 역할 지시문과 정책은 일반판이다. 자기 팀 규칙은 S3에서 채운다.
