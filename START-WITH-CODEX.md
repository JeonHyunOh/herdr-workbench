# Codex로 시작하기 (윈도우)

이 문서는 윈도우에서 Codex를 쓰는 사람이 이 레포의 작업 환경을 참고해 자기 환경을 만들도록 안내한다. 원본을 그대로 옮기는 것이 목표가 아니다. 원본의 구조를 보고 자기 일에 필요한 만큼 골라 세운다.

| 단계 | 하는 사람 | 결과 |
|---|---|---|
| 1. Herdr 알기 | 사람이 읽는다 | Herdr와 이 작업대가 무엇인지 안다 |
| 2. 설치 | 사람이 PowerShell에서 한다 | Herdr·Codex 설치와 로그인, 이 레포 받기 |
| 3. 킥오프 브리핑 | Codex | 이 환경 설명과 이 PC 점검 결과(`my-setup/01-kickoff.md`) |
| 4. 심층 인터뷰와 구축 | Codex와 사람 | 내 환경 설계서(`my-setup/03-design.md`)와 단계별 구축 |

3·4단계는 아래 프롬프트를 Codex 입력창에 붙여 넣어 진행한다. 기록은 모두 레포 안 `my-setup/` 폴더에 남는다. 이 폴더는 `.gitignore`에 들어 있어 git이 추적하지 않는다. 그래도 이 레포에는 push하지 않는다.

## 1. Herdr란

Herdr는 터미널과 코딩 에이전트를 위한 데스크톱 앱이다. Codex나 Claude Code 같은 명령줄 에이전트를 여러 개 열어 두고, 어느 에이전트가 사람의 답을 기다리는지 한 목록에서 본다. 2개 프로그램으로 나뉜다.

- **Herdr 앱**: 창이다. 터미널을 스페이스·탭·패널로 배치한다. Agents 목록은 에이전트마다 상태를 보여 준다. 상태는 Working(작업 중), Blocked(사람의 답을 기다림), Done(사람이 보지 않는 사이에 끝남), Idle(쉬는 중, 또는 끝난 뒤 사람이 확인함)이다.
- **herdr-core(`hc`)**: 터미널을 실제로 돌리는 프로그램이다. 창을 닫아도 터미널과 그 안의 에이전트는 계속 돈다. 에이전트는 `hc run`으로 다른 에이전트를 열고, `hc send`로 일을 보내고 답을 받는다. 이렇게 열린 에이전트는 연 에이전트의 자식으로 기록된다.

처음 보는 용어는 다음과 같다.

- **스페이스**: 한 컴퓨터에서 하는 일의 묶음이다. 보통 레포 하나에 스페이스 하나를 둔다.
- **탭과 패널(pane)**: 스페이스 안의 화면 나눔이다. 패널을 닫으면 그 터미널도 끝난다.
- **mod**: 패널·메뉴·대화상자를 그리는 작은 JavaScript 프로그램이다. **레이아웃**은 창의 배치다.

에이전트 일에서 Herdr가 주는 것은 3가지다.

1. 에이전트 여러 개를 한 창에서 본다. Blocked 표시로 내 답이 필요한 세션을 바로 찾는다.
2. 창을 닫거나 다른 일을 해도 에이전트는 계속 일한다. 단, 재부팅 뒤에는 패널이 같은 폴더의 새 셸로 열리고 이전 프로그램은 다시 열리지 않는다.
3. 에이전트가 하위 에이전트를 열고 결과를 받는다. 사람이 세션 사이에서 내용을 옮겨 적지 않아도 된다.

### 이 레포의 작업대가 더한 것

이 레포의 작업대는 Herdr 위에 다음을 더했다. 구조는 [docs/01-what-is-this.md](docs/01-what-is-this.md)와 [세션 계층 체계도](docs/04-session-hierarchy.md)에 있다.

- **bench**: 디렉터 → 리드 → 작업자 3계층을 도구로 지킨다. 누가 누구를 열 수 있는지, 지시는 등록된 부모만 보내는지, 보고가 부모 수신함으로 가는지, 끝난 세션을 어떤 조건에서 정리하는지를 bench가 검사한다.
- **역할 지시문 5개와 정책 파일**: 계층마다 맡는 일과 보고 방법, 에이전트가 사람 승인 없이 해도 되는 일의 경계를 적는다.
- **화면 mod**: 세션 트리, md를 렌더링하는 Files 패널, 터미널 우클릭 'Files에서 열기', md 뷰어, 내 PR 패널이다.

에이전트가 에이전트를 여는 일은 Herdr 기본 기능만으로도 된다. bench는 그 위에 계층 규칙, 수신함, 정리 조건을 더한다. 그래서 4절에서 어디까지 쓸지 고른다.

### 윈도우에서 지금 되는 것 (2026-11-18 확인)

| 구성 요소 | 윈도우 상태 | 근거 |
|---|---|---|
| Herdr 앱·`hc` | 공식 지원. x64, Windows 10 1803 이상 | [Herdr README](https://github.com/herdrdev/herdr-app) |
| Codex CLI | 공식 지원. PowerShell에서는 윈도우 샌드박스를, WSL2 안에서는 리눅스 샌드박스를 쓴다 | [Codex 윈도우 문서](https://developers.openai.com/codex/windows) |
| Codex 상태 표시 | 이 레포를 만든 맥에서는 Codex 세션이 Agents 목록에 working·done으로 보인다. 윈도우는 확인하지 않았다 | 맥 실측(`hc get review`) |
| bench·역할·정책 | WSL2는 우분투 24.04 컨테이너에서 시험 174개가 통과했다. 윈도우 직접은 이식이 필요하고 해 본 적 없다(docs/02 B1~B16) | [docs/02-platform-points.md](docs/02-platform-points.md) |
| 화면 mod | 맥 Herdr 0.1.15에서만 확인했다. 윈도우는 이식이 필요하다(docs/02 M1~M6) | [wsl2/known-gaps.md](wsl2/known-gaps.md) |

## 2. 설치

사람이 PowerShell에서 직접 한다. 회사 PC라면 설치가 허용되는지 먼저 확인한다. 항목별 확인 방법은 [PC 점검표](docs/00-checklist.md)에 있다.

### 2-1. 먼저 볼 것

- CPU가 x64인지 본다. PowerShell에서 `$env:PROCESSOR_ARCHITECTURE`가 `AMD64`면 된다. Herdr 윈도우판은 x64만 있다.
- Herdr는 Windows 10 1803 이상이 필요하다. Codex는 Windows 11을 권장하고, Windows 10이면 1809 이상이 필요하다.
- Herdr 설치기는 `curl.exe`와 `tar.exe`를 쓴다.
- PowerShell 7을 권장한다. Herdr 터미널의 기본 셸은 PowerShell 7이고, 없으면 Windows PowerShell을 쓴다. Codex GitHub 이슈에 Microsoft Store판 PowerShell 7에서 샌드박스 명령이 'Access is denied'로 실패했다는 보고가 있다([#9062](https://github.com/openai/codex/issues/9062), [#60397](https://github.com/openai/codex/issues/60397)). 같은 증상이면 MSI판 PowerShell 7을 쓴다.
- Git for Windows를 설치한다. 레포를 받을 때 필요하고, `hc`의 템플릿과 따옴표로 묶은 셸 명령은 PATH에서 `sh`를 찾는다. Git for Windows가 `sh`를 준다.

### 2-2. Herdr 설치

```powershell
irm https://releases.herdr.dev/app/install.ps1 | iex
```

- 시작 메뉴에 Herdr가 생긴다. 설치기가 `%LOCALAPPDATA%\Programs\herdr-app`을 사용자 PATH에 넣으므로 새 PowerShell 창을 연다. herdr-core가 없으면 같이 설치한다.
- 설치 스크립트는 코드를 내려받아 실행한다. 먼저 읽어 보려면 [install.ps1](https://github.com/herdrdev/herdr-app/blob/main/distribution/install.ps1)을 연다.
- 새 PowerShell 창에서 `herdr-app --version`과 `hc --version`이 버전을 출력하는지 본다. 이 레포를 만든 맥은 Herdr 앱 0.1.16, `hc` 0.1.21이다(11/18).
- 사용 통계 전송은 기본으로 켜져 있다. 끄려면 Settings → Privacy에서 끈다.

### 2-3. Codex 설치와 로그인

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"
```

Node.js가 있으면 `npm install -g @openai/codex`로도 설치할 수 있다.

- `codex`를 실행하고 **Sign in with ChatGPT**를 고른다. API 키로 로그인하지 않는다. API 키로 로그인하면 사용량이 구독이 아니라 API 요금으로 청구된다.
- 명령을 처음 실행할 때 윈도우 샌드박스 설정을 물을 수 있다. 관리자 승인이 필요한 방식이 있으므로 회사 정책에 맞게 고른다. 승인 창에는 사람이 답한다.
- `codex --version`이 버전을 출력하는지 본다. 이 레포를 만든 맥은 0.169.0이다(11/18).

### 2-4. 이 레포 받기

```powershell
git clone <받은 레포 주소> herdr-workbench
```

비공개 레포라 보낸 사람의 초대를 먼저 받아야 한다. 초대받은 계정에는 push 권한도 생기지만, 이 레포에는 push하지 않는다. 내 기록은 `my-setup/`에 남는다.

### 2-5. Herdr에서 Codex 열기

1. Herdr를 연다. 터미널에서 `cd`로 `herdr-workbench` 폴더에 들어간다. 이름을 붙이지 않은 스페이스는 첫 터미널의 폴더를 따른다.
2. Herdr 메뉴에서 Codex를 열거나, 터미널에 `codex --no-daemon`을 입력한다. 메뉴로 열면 Herdr가 이 옵션을 붙인다. 이 옵션이 없으면 Codex가 공유 백그라운드 서버를 쓴다. 그러면 나중에 연 세션이 첫 터미널의 신원으로 돌고, 첫 터미널이 끝날 때 같이 멈출 수 있다(Herdr 안내).
3. 처음 열면 Codex가 이 폴더를 믿을지(Trust this folder?) 묻는다. 폴더 경로가 받은 `herdr-workbench`인지 확인하고 사람이 고른다. 믿으면 Codex가 이 폴더의 파일을 읽고 고치고 실행할 수 있고, 폴더 설정이 있으면 그것도 실행된다. 이 레포에는 폴더 설정(`.codex/`)이 없고, 루트의 [AGENTS.md](AGENTS.md)는 Codex가 자동으로 읽는 지시 파일이다.
4. Agents 목록에 이 Codex가 보이는지 본다. 보이면 Codex가 일하는 동안 Working, 끝나면 Done, 승인을 기다리면 Blocked로 바뀌는지도 본다. 보이지 않아도 3·4절은 진행할 수 있다. 본 결과는 킥오프 때 Codex에 알려 준다.
5. 승인은 기본 방식(필요할 때 묻기)으로 둔다. 승인과 샌드박스를 함께 끄는 `--dangerously-bypass-approvals-and-sandbox`는 쓰지 않는다.

Codex가 "사람이 실행한다"고 안내하는 명령은 Herdr에 PowerShell 탭을 하나 더 열어 거기서 실행하고, 출력을 Codex에 붙여 준다.

## 3. 킥오프 브리핑

Codex 입력창에 아래를 붙여 넣는다. 이 단계에서 Codex는 `my-setup/01-kickoff.md` 1개만 만든다.

```text
이 폴더는 다른 사람의 Herdr 작업 환경을 공유하는 자료다. 나는 윈도우에서 Codex를 쓰고, 이 환경을 참고해 내 환경을 만들려고 한다. 지금은 킥오프 브리핑만 받는다.

지킬 것
- docs/03-safety-rules.md를 이 세션 내내 지킨다. 로그인 정보·API 키·토큰을 읽거나 출력하지 않는다. 승인 창은 내가 답한다.
- 이 단계에서는 my-setup/01-kickoff.md 1개만 만든다. 다른 파일과 설정은 바꾸지 않고, 명령은 읽기만 쓴다.
- 한국어 존댓말로 답한다. 문서와 명령 출력에 없는 사실은 '확인 필요'로 적고 지어내지 않는다.

읽을 것
- START-WITH-CODEX.md, README.md, docs/00~04, wsl2/known-gaps.md
- reference/roles/의 5개 파일, reference/policy.example.yaml
- 이 PC에 설치된 Herdr 안내: hc --skill, herdr-app --skill 출력

이 PC에서 확인할 것 (읽기 명령만, 실패하면 실패한 출력 그대로 적는다)
$env:PROCESSOR_ARCHITECTURE, [Environment]::OSVersion.Version, $PSVersionTable.PSVersion, herdr-app --version, hc --version, codex --version, git --version, Get-Command sh, python --version 또는 py -3 --version, wsl --status

브리핑 순서 (항목마다 짧게)
1. Herdr가 무엇이고, 이 작업대가 그 위에 무엇을 더했는지
2. 디렉터·리드·작업자 3계층과, 사람이 어디서 대화하고 지시하는지
3. 이 작업대에서 일 1건이 처음부터 끝까지 흐르는 예시
4. 이 PC 확인 결과와, 윈도우에서 되는 것·이식이 필요한 것·확인 안 된 것
5. START-WITH-CODEX.md 4-1의 구축 단계 1~4가 각각 무엇을 주고 무엇이 드는지, 이 PC 조건에서 바로 할 수 있는 단계
6. 원본 환경에서 사람이 정한 것(자율 경계, 모델 배분, 보고 방식, 계층 구조) 중 내가 정해야 할 것 목록

브리핑을 같은 순서로 my-setup/01-kickoff.md에 적는다. 끝나면 내 질문을 받고, 질문이 끝나면 4절 심층 인터뷰를 시작할지 묻는다.
```

사람이 확인할 것은 3가지다.

- 브리핑이 6개 항목을 모두 다뤘는가
- PC 확인 결과가 실제 명령 출력인가(출력에 없는 버전이 적혀 있지 않은가)
- `my-setup/01-kickoff.md`를 열어 6개 항목이 있는가. `my-setup/`은 무시 목록에 있어 일반 `git status`에는 나오지 않는다. 생긴 파일은 `git status --short --ignored --untracked-files=all`로, 바뀐 파일이 없는지는 `git diff --stat`으로 본다

## 4. 심층 인터뷰와 내 환경 구축

### 4-1. 구축 단계

단계는 아래에서 위로 쌓인다. 1·2단계로 먼저 써 보고 3단계가 필요한지 정하는 것을 권한다.

| 단계 | 더하는 것 | 윈도우 상태 | 드는 것 |
|---|---|---|---|
| 1. Herdr + Codex 여러 세션 | 사람이 탭·패널에 Codex를 열고 Agents 목록으로 상태를 본다 | Herdr·Codex 자체는 공식 지원이다. Codex 상태 표시는 윈도우에서 확인하지 않았다 | 2절 설치뿐 |
| 2. 내 규칙 | 내 AGENTS.md(전역 `%USERPROFILE%\.codex\AGENTS.md` 또는 작업 폴더), 역할 지시문, 자율 경계 표. Codex가 `hc run`으로 하위 세션을 열고 `hc send`로 보고를 받는다 | Herdr·Codex 공식 기능 범위다. 일부 `hc` 명령은 `sh`가 필요하다. 윈도우에서 해 본 적은 없다 | 인터뷰 결과로 문서를 쓴다. 도구 설치는 없다 |
| 3. bench | 계층 규칙 검사, 수신함과 확인(ack), 정리 조건, 세션 상태 파일 | WSL2는 리눅스 컨테이너에서 검증했다. 윈도우 직접은 이식이 필요하고 해 본 적 없다 | WSL2 설정, 또는 이식 작업(SETUP-WITH-CLAUDE.md S2-B) |
| 4. 화면 mod | 세션 트리, md를 렌더링하는 Files, 메뉴, md 뷰어, PR 패널 | 확인하지 않았다(docs/02 M1~M6). WSL2에서는 보류다 | mod 이식과 `herdr-app check` |

### 4-2. Codex만으로 bench를 쓸 때

bench 코드(`reference/workbench/bench.py`)와 역할 지시문에서 확인한 내용이다. 둘째 항목은 맥에서 시험 설치본으로도 확인했다(11/18).

- bench는 벤더를 정하지 않으면 디렉터와 리드를 Claude로, 작업자를 Codex로 연다. Codex만 쓰려면 디렉터·리드·작업자를 열 때마다 `spawn --vendor codex --model <Codex 모델>`을 준다. 내 역할 지시문에도 이 규칙을 적는다.
- `bench.yaml`에는 Claude 항목(경로와 기본 모델)이 있어야 bench가 설정을 읽는다. Claude를 설치하지 않았으면 경로는 자리표시자로 남아도 된다. Claude 세션을 열지 않는 한 그 경로는 쓰이지 않는다. Claude 경로를 없는 경로로 둔 설치본에서 Codex 디렉터 `spawn --dry-run`이 정상인 것을 확인했다.
- bench가 Codex를 열 때 샌드박스는 리드와 코딩 작업자가 `workspace-write`, 디렉터와 검토·조사 작업자가 `read-only`다. Codex용 bench MCP 도구는 보고·수신함·확인 3가지뿐이다. 그래서 Codex 디렉터나 리드는 하위 세션을 열고(spawn), 지시하고(send), 닫는(close) 일을 CLI로 한다. 이 명령은 수신함에 쓴다. 수신함이 작업 폴더 밖에 있거나 세션이 `read-only`면 샌드박스 밖 쓰기가 되어 승인 요청이 뜬다.
- 같은 대화를 다시 여는 `--resume`은 Claude 세션만 된다. Codex 세션은 재시작하면 상태 파일을 읽고 새로 시작한다. Codex 디렉터와 리드는 `spawn --state-file <절대 경로>`로 상태 파일을 정해 둔다.

원본 환경은 디렉터를 Claude로 두고, Codex는 작업자와 일부 리드로 쓴다.

### 4-3. 승인 요청을 누가 판단하나

이 안내의 기본은 사람이 Codex의 승인 요청에 직접 답하는 것이다(docs/03 2번). Codex에는 승인 요청을 Codex의 자동 검토가 대신 판단하게 하는 기능도 있다. 설정 파일의 `approvals_reviewer = "auto_review"`와 실행 옵션 `--approve-for-me`가 그것이다. 원본 환경은 설정 파일로 이 기능을 켜 두었다.

이 기능을 켜면 docs/03 2번의 '승인 창은 사람이 답한다'에 예외를 두는 것이다. 켤지, 켠다면 어떤 일에 쓸지는 인터뷰 C에서 사람이 정하고 설계서 4번에 적는다. 원본에 켜져 있다는 이유로 받는 사람에게 켜지 않는다. 다음 3가지는 이 기능을 켜도 예외가 아니다.

- trust 질문(Trust this folder?)에는 사람이 답한다.
- 에이전트가 다른 세션의 승인 창에 키 입력으로 답하지 않는다.
- 승인과 샌드박스를 함께 끄는 `--dangerously-bypass-approvals-and-sandbox`를 쓰지 않는다.

### 4-4. 인터뷰

킥오프가 끝난 같은 세션에 아래를 붙여 넣는다. 세션이 끊겼으면 새 Codex 세션에서 맨 아래 '끊겼을 때 이어 하기'부터 한다.

```text
START-WITH-CODEX.md 4절과 my-setup/01-kickoff.md를 읽는다. my-setup/02-interview.md나 03-design.md가 이미 있으면 그것도 읽고, 끝난 주제는 다시 묻지 않고 남은 주제부터 이어 간다. 03-design.md를 내가 이미 승인했다면 인터뷰를 다시 하지 않고 그 사실을 알린다. 그다음 나에게 맞는 작업 환경을 정하는 심층 인터뷰를 진행한다.

진행 방식
- 한 번에 질문은 1~2개만 한다. 내 답을 듣고 다음 질문을 고른다.
- 질문마다 왜 묻는지 1줄, 원본 환경은 어떻게 했는지 1줄을 붙인다. 원본은 참고이고 기본값이 아니다.
- 내가 모른다고 하면 선택지 2~3개와 각각을 골랐을 때의 결과를 보여 준다. 내 답을 추측으로 채우지 않는다.
- 주제 하나가 끝나면 이해한 내용을 3~5줄로 요약해 맞는지 확인받고, my-setup/02-interview.md에 덧붙인다. 앞서 적은 내용은 지우지 않는다.
- 인터뷰 동안에는 my-setup/ 밖의 파일과 설정을 바꾸지 않는다.

주제 (내 답에 따라 순서를 바꿔도 된다)
A. 내 일: 주로 하는 일(코딩·리뷰·문서·조사·운영 등), 다루는 레포와 위치, 하루에 동시에 진행하는 일의 수, 팀의 브랜치·PR·리뷰 규칙
B. 지금 방식의 불편: 지금 Codex를 어떻게 쓰는지, 어디서 시간이 새는지, 세션 사이에서 내가 손으로 옮기는 것
C. 사람의 개입: 내가 직접 정할 것, 에이전트가 알아서 해도 되는 일, 먼저 보여 주고 승인받을 일, 하지 않을 일, Codex 승인 요청을 내가 답할지 자동 검토에 맡길지(4-3)
D. 세션 구조: 나 + Codex 여러 개 / 나 + 리드 + 작업자 / 디렉터·리드·작업자 3계층 중 무엇이 맞는지, 동시 세션 수와 리드당 작업자 수의 상한
E. 모델과 도구: Codex만 쓸지 Claude Code도 쓸지(Codex만 쓰면 4-2), 기획·구현·검토·글쓰기에 쓸 모델(Codex /model 목록에서 고른다), 다른 모델의 교차 검토, 구독 사용량 한도
F. 보고: 언제 받을지(끝날 때·막힐 때·결정이 필요할 때), 길이와 형식, 언어와 문체, 결과 파일 위치
G. PC와 회사 조건: WSL2 사용 가능 여부, 관리자 권한, 보안 정책, 쓸 수 있는 도구
H. 화면: 레이아웃, 필요한 패널(파일·md·PR)
I. 안전: docs/03-safety-rules.md의 6개 규칙은 고정이다. 예외는 C에서 정하는 Codex 자동 승인 검토 하나뿐이다. 더 막을 것만 묻는다.

인터뷰가 끝나면 my-setup/03-design.md에 내 환경 설계서를 쓴다.
1. 목적: 이 환경으로 줄이려는 수고(내 말로)
2. 고른 구축 단계와 이유, 고르지 않은 단계와 이유
3. 세션 구조: 계층, 역할마다 이름·하는 일·벤더·모델·여는 사람
4. 자율 경계 표: 자율 / 보여 주고 승인 뒤 / 하지 않음. 승인 요청을 누가 판단하는지 포함
5. 보고 규칙
6. 화면
7. 이 레포에서 가져올 파일과 고칠 곳
8. 구축 계획: 단계마다 실행할 머신과 셸, 만들 파일, 바꿀 설정(경로와 내용), 확인 방법
9. 확인 안 된 것과 위험

설계서를 보여 주고 내가 승인하기 전에는 구축을 시작하지 않는다.
```

사람이 확인할 것은 설계서의 2·4·8번이다. 고른 단계가 내 PC 조건(G)과 맞는지, 자율 경계 표가 내가 답한 대로인지, 구축 계획의 단계마다 실행할 위치와 확인 방법이 있는지 본다.

### 4-5. 구축

고른 단계에 따라 따를 절차가 다르다.

| 고른 단계 | 따를 절차 |
|---|---|
| 1까지 | 2절 설치로 끝난다. 설계서의 사용법만 `my-setup/build/`에 정리한다 |
| 2까지 | 아래 '2단계 기준' |
| 3까지 | SETUP-WITH-CLAUDE.md S1 → 아래 '3단계 사전 점검' → S2(A 또는 B) → S3 → S5 |
| 4까지 | 3단계 절차에 S4를 더한다. WSL2 경로에서 S4는 보류다(wsl2/known-gaps.md). 설계서에는 고른 것으로 적되 끝난 것으로 보지 않는다 |

**2단계 기준**

- reference/roles/의 역할 지시문은 bench를 전제로 쓴 것이다. bench 명령과 MCP 보고 부분을 `hc` 명령으로 바꾼 내 판을 `my-setup/build/roles/`에 만든다.
- 하위 세션은 `hc run --bg --name <이름> --cwd <폴더> codex --no-daemon "<지시>"`처럼 연다. 이 모양은 맥의 `hc --skill` 예시이고, Codex는 `--no-daemon`이 있어야 그 명령이 `hc` 터미널 안에서 돈다. 윈도우에서는 해 본 적 없다.
- 안전 규칙 5번(자식 환경에서 API 키 환경변수 제거)을 PowerShell의 `hc run`에서 어떻게 지킬지는 확인하지 않았다. 구독 로그인만 쓰고 API 키 환경변수를 두지 않으면 지울 것이 없다. 키 값은 확인하지 않는다. 이 점을 설계서 9번에 적는다.
- 확인 방법: 하위 세션이 실제로 열리는지, 첫 지시가 도착하는지, 보고가 부모에게 도착하는지, 승인 창에 사람이 답했는지를 `my-setup/04-build-log.md`에 적는다.

**3단계 사전 점검**

SETUP-WITH-CLAUDE.md S1을 마치고 S2에 들어가기 전에 다음 값을 `my-setup/04-build-log.md`에 적는다. 빈 값이 있으면 S2를 시작하지 않는다.

- 경로: 윈도우 직접 또는 WSL2. WSL2면 사람이 wsl2/README.md 1~3절을 먼저 마치고, Herdr에서 WSL 머신 터미널을 연 뒤 그 안에서 Codex를 다시 연다. 새 Codex 세션은 '끊겼을 때 이어 하기'로 이어 간다.
- 실행할 머신과 셸, 스페이스 id, `hc`·`codex` 경로, Python 이름과 PyYAML·tzdata 확인 결과, Codex 기본 모델(S1에서 확인한다)
- Codex만 쓰는지(4-2), 설치 폴더와 디렉터가 일할 폴더

**SETUP-WITH-CLAUDE.md를 따를 때 바꿔 읽는 것**

| 그 파일 | 이 안내에서 |
|---|---|
| 'Claude'(세팅하는 세션) | 이 Codex 세션 |
| '사람이 `!`로 실행한다' | 사람이 Herdr의 다른 탭(윈도우 직접은 PowerShell, WSL2는 WSL 터미널)에서 실행하고 출력을 붙인다 |
| `setup-notes.md` | `my-setup/04-build-log.md` |
| `INSTALL`(설치 폴더의 절대 경로) | 그대로. 윈도우 직접이면 레포 아래 `port/`이고, 이 폴더는 무시 목록에 있다 |
| S5의 `spawn --role secretary --vendor claude --model <Claude 모델>` | Codex만 쓰면 `--vendor codex --model <Codex 모델> --state-file <절대 경로>` |

구축을 시작할 때 아래를 붙여 넣는다.

```text
my-setup/03-design.md의 구축 계획을 START-WITH-CODEX.md 4-5에 따라 한 단계씩 진행한다.

- 단계마다 실행할 위치, 만들 파일, 바꿀 설정의 경로와 내용을 먼저 보여 주고 내 승인을 받는다.
- 내 설정 파일(%USERPROFILE%\.codex\ 아래 파일, PowerShell 프로필, Herdr 설정)에 들어갈 내용은 my-setup/build/ 아래에 먼저 만든다. 제자리로 옮기는 일은 내가 직접 하거나, 미리보기와 적용이 나뉜 스크립트를 만들어 내가 실행한다. 스크립트는 바꿀 파일 목록을 출력하고, 덮어쓰기 전에 원래 파일을 백업한다.
- 3단계 이상이면 4-5의 '3단계 사전 점검'을 먼저 채운다. 빈 값이 있으면 멈추고 묻는다. SETUP-WITH-CLAUDE.md는 4-5의 '바꿔 읽는 것' 표대로 읽고, 표에 없는 Claude 전용 지시를 만나면 멈추고 묻는다.
- 단계가 끝날 때마다 확인 방법을 실제로 실행하고, 명령과 결과를 my-setup/04-build-log.md에 적는다.
- 막히면 멈추고, 어느 단계에서 무엇이 실패했는지와 출력을 남긴다.
```

## 끊겼을 때 이어 하기

새 Codex 세션을 레포 폴더에서 열고 아래를 붙여 넣는다.

```text
START-WITH-CODEX.md와 my-setup/ 아래 파일을 모두 읽는다. 01-kickoff·02-interview·03-design·04-build-log 중 어디까지 끝났는지, 설계서를 내가 승인했는지, 다음에 할 일이 무엇인지 3줄로 말한다. 내 확인을 받은 뒤 해당 절(4-4 인터뷰 또는 4-5 구축)의 규칙으로 이어 간다. 앞서 적은 기록은 지우지 않는다. docs/03-safety-rules.md를 지킨다.
```

## 이 문서에 없는 것

- 윈도우 실기 결과. 이 문서의 윈도우 내용은 Herdr와 Codex 공식 문서, 그리고 맥과 리눅스 컨테이너에서 확인한 사실을 바탕으로 썼다. 받는 사람의 첫 설치가 첫 윈도우 시험이다.
- 원본 환경의 팀 전용 규칙과 개인 설정. 역할 지시문과 정책은 일반판이다.
