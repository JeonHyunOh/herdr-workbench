# 갈래 1. WSL2 머신으로 설치

Herdr 앱은 윈도우에 두고, herdr-core·bench·Claude Code·Codex는 WSL2 우분투(윈도우 안에서 도는 리눅스) 안에 둔다. Herdr 앱은 ssh로 다른 머신을 붙여 그 머신의 터미널을 보여 준다. 이 갈래는 WSL2를 그런 머신으로 붙인다. bench는 리눅스에서 코드 변경 없이 돈다.

이 갈래는 **준비 단계**다. 트리·Files·메뉴 mod가 WSL 머신을 가리키게 하는 변경이 아직 없다. 그 전까지 되는 것과 안 되는 것은 [known-gaps.md](known-gaps.md)에 있다. 윈도우 실기에서는 아직 따라 해 보지 않았다. 리눅스 부분(4~6단계)은 우분투 24.04 컨테이너에서 확인했다.

먼저 [PC 점검표](../docs/00-checklist.md) 1번(WSL2를 켤 수 있는지)을 확인한다. [안전 규칙](../docs/03-safety-rules.md)을 모든 단계에 적용한다.

## 1. WSL2와 우분투 (윈도우, 사람)

- WSL2와 우분투를 설치한다. 관리자 권한과 사내 정책을 따른다.
- 우분투 안에서 systemd가 켜져 있어야 2단계의 커뮤니티 도구를 쓸 수 있다.
- 윈도우 OpenSSH 클라이언트가 있어야 한다(PowerShell `Get-Command ssh`).

## 2. Herdr 앱과 WSL 머신 (윈도우, 사람)

- Herdr 앱을 설치한다. 설치 명령은 [herdr-app README](https://github.com/herdrdev/herdr-app)의 Windows 절을 따른다. 앱 설치기는 herdr-core가 없으면 같이 설치한다. 윈도우판은 x86_64만 있다.
- WSL을 Herdr 머신으로 붙인다. 방법은 2가지다. 둘 다 WSL 안에 SSH 서버를 켜고 SSH 키를 만들기 때문에 사람 설정이 바뀐다. 문서를 읽고 사람이 직접 실행한다.
  - 커뮤니티 mod [emoss08/herdr-wsl](https://github.com/emoss08/herdr-wsl): 단계마다 묻고, 이미 된 단계는 건너뛴다. SSH 서버를 localhost·키 로그인으로만 연다고 적혀 있다.
  - 직접: `hc machine add <머신 이름> --install` (herdr-wsl README가 내부에서 쓰는 명령. 이 묶음에서 따로 확인하지 않았다).
- Herdr 앱에서 그 머신에 스페이스를 하나 만든다. 앱이 보여 주는 스페이스 id에 `<머신 이름>/` 접두가 붙어 있으면 접두를 뗀 값이 5단계의 `--space-id`다. 스페이스 id를 앱에서 읽는 방법은 확인 필요다(macOS에서는 `herdr-app status`의 `space`).

## 3. WSL 안의 도구 (우분투, 사람)

```sh
sudo apt update
sudo apt install -y python3 python3-yaml git procps tzdata
```

- Claude Code와 Codex를 설치하고 각자 구독 계정으로 로그인한다(Claude 구독, ChatGPT 구독). API 키로 로그인하지 않는다. bench는 Codex를 `forced_login_method="chatgpt"`로 띄운다.
- `hc --version`이 WSL 안에서 되는지 본다. 2단계가 herdr-core를 WSL에 깔았어야 한다.
- 이 묶음을 WSL 안으로 받는다(예: `git clone <묶음 레포 주소> ~/herdr-workbench`). 레포 접근은 받는 사람 자신의 GitHub 로그인을 쓴다.

## 4. 설치 미리보기 (우분투)

```sh
mkdir -p ~/work            # 디렉터가 일할 폴더. 레포들을 이 아래에 둔다
python3 ~/herdr-workbench/wsl2/setup.py --target ~/workbench --hub ~/work --space-id <스페이스 id>
```

미리보기는 아무것도 쓰지 않는다. 찾은 도구 경로, 만들 파일, `bench.yaml` 전체 내용, 건드리지 않는 곳(`~/.claude`, `~/.codex`, `~/.config/herdr-app`, 셸 프로필)을 보여 준다. `codex 실제 실행 파일`을 찾지 못하면 `--codex-process <경로>`로 넣는다(npm 전역 설치의 `@openai/codex` 아래 `node_modules/@openai/codex-linux-*/vendor/*/` 안에 있다).

## 5. 설치 적용 (우분투)

같은 명령에 `--apply`를 붙인다. `--target` 폴더가 이미 있으면 쓰지 않고 멈춘다. 적용 뒤 설치한 폴더에서 bench 시험을 돌려 결과를 보인다.

시험만 다시 돌리려면 이렇게 한다.

```sh
cd ~/workbench/workbench
python3 -m unittest discover -s tests -p 'test_*.py'
```

컨테이너에서 확인한 결과: 시험 174개 통과(git 기본 브랜치 설정 없는 상태).

## 6. 첫 디렉터 띄우기 (Herdr 앱의 WSL 스페이스 터미널)

2단계에서 만든 WSL 스페이스의 터미널에서 실행한다.

```sh
python3 ~/workbench/workbench/bench.py --config ~/workbench/workbench/bench.yaml spawn --role secretary --vendor claude --model claude-opus-5-5 --cwd ~/work --display 디렉터
python3 ~/workbench/workbench/bench.py --config ~/workbench/workbench/bench.yaml ls
```

Claude Code가 처음 그 폴더를 열 때 trust 질문을 띄우면 사람이 답한다. 디렉터에게 할 일을 주면 디렉터가 리드를, 리드가 작업자를 연다. 역할 지시문은 `~/workbench/roles/`, 정책은 `~/workbench/policy.yaml`이다.

## 7. 트리·패널 mod (보류)

트리·Files·메뉴 mod는 윈도우 앱 안에서 돈다. 지금 생성기는 bench 파일을 앱과 같은 컴퓨터에서 읽는다. WSL 머신을 가리키게 하는 변경이 들어오면 이 절을 채운다. 그 전까지는 Herdr 기본 Agents 패널을 쓴다. Herdr 문서에 따르면 기본 패널도 `hc run`으로 연 자식 터미널을 부모 아래에 보여 준다. WSL 머신에서 그렇게 보이는지는 확인하지 않았다. 역할·모델 표시와 안 읽은 보고 수는 `bench ls`로 본다.
