# 00. PC 점검표

## 1. WSL2 사용 가능 여부

- **확인 방법:** PowerShell에서 `wsl --status`와 `wsl --list --verbose`를 실행해 WSL 상태와 설치된 배포판의 버전을 확인한다. 관리자 권한이 필요한 설치·설정이 허용되는지, 사내 보안 정책이 WSL2를 허용하는지도 확인한다. 명령이 실패하거나 배포판이 없으면 WSL2 사용 가능 여부를 별도로 확인한다.
- **안 되면:** 관리자 또는 보안 담당자에게 확인한다. 허용되지 않거나 켤 수 없으면 Windows 직접 이식 경로를 선택한다. 임의로 정책을 우회하지 않는다.

## 2. CPU 아키텍처

- **확인 방법:** PowerShell에서 `$env:PROCESSOR_ARCHITECTURE`를 확인한다. `AMD64`는 x64를 뜻한다. Herdr Windows판은 x86_64만 제공한다.
- **안 되면:** x64가 아니거나 결과가 모호하면 장치 사양을 확인한다. 지원 여부가 확인될 때까지 설치를 멈춘다.

## 3. Windows와 기본 도구

- **확인 방법:** `winver`로 Windows 버전을 확인한다. Herdr 설치에는 Windows 10 1803 이상과 `curl`, `tar`가 필요하다. PowerShell에서 `Get-Command curl.exe, tar.exe`로 명령을 찾는지 확인한다.
- **안 되면:** 회사 정책에 맞춰 Windows와 도구를 준비한다. 요구 조건을 충족하지 못하면 설치를 멈춘다.

## 4. PowerShell 7

- **확인 방법:** `pwsh -NoProfile -Command '$PSVersionTable.PSVersion'`의 주 버전이 7인지 확인한다.
- **안 되면:** 회사에서 허용한 방법으로 PowerShell 7을 설치하거나 관리자에게 요청한다.

## 5. Git for Windows

- **확인 방법:** `git --version`과 `Get-Command git`으로 버전과 실행 위치를 확인한다. Git for Windows 설치 여부는 설치 목록에서도 확인한다.
- **안 되면:** 회사에서 허용한 방법으로 설치한다. 실행 경로가 잡히지 않으면 새 터미널에서 다시 확인한다.

## 6. Python 3와 PyYAML

- **확인 방법:** `python --version`과 `python -c "import yaml; print(yaml.__version__)"`을 실행한다. Python 3와 PyYAML, tzdata가 필요하다. `close`는 정책 파일을 읽을 때 PyYAML을 사용한다. bench는 import할 때 시간대 'Asia/Seoul'을 읽는데, 윈도우 Python에는 시간대 데이터가 없어 tzdata 패키지가 있어야 한다. `python -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Seoul')"`가 오류 없이 끝나는지 본다. 윈도우에서는 `python` 대신 `py -3`만 있을 수 있다.
- **안 되면:** 허용된 방법으로 Python 3와 PyYAML을 준비한다. 설치가 제한되면 관리자에게 요청한다.

## 7. Claude Code와 구독 로그인

- **확인 방법:** `claude --version`으로 실행을 확인하고 Claude Code를 열어 구독 계정의 로그인 상태를 화면에서 확인한다. 비밀값은 열거나 출력하지 않는다.
- **안 되면:** 허용된 방법으로 설치하고 사람이 구독 계정에 직접 로그인한다.

## 8. Codex와 ChatGPT 구독 로그인

- **확인 방법:** `codex --version`으로 실행을 확인하고 Codex를 열어 ChatGPT 구독 계정의 로그인 상태를 화면에서 확인한다. API 키 로그인은 사용하지 않는다.
- **안 되면:** 허용된 방법으로 설치하고 사람이 ChatGPT 계정에 직접 로그인한다.

## 9. Herdr 앱

- **확인 방법:** Herdr 앱을 열고 버전을 확인한다. PowerShell에서 `herdr-app --version`과 `hc --version`도 확인한다. Windows에서의 명령 이름과 경로는 **확인 필요**다.
- **안 되면:** 허용된 방법으로 앱과 herdr-core를 설치한다. 명령을 찾지 못하면 설치 위치와 명령 이름을 확인한 뒤 진행한다.

## 경로 선택

| WSL2 점검 결과 | 선택 | 다음 단계 |
|---|---|---|
| WSL2를 켤 수 있음 | `wsl2/` | 해당 안내의 준비 여부를 확인하고 따른다. |
| WSL2를 켤 수 없음 | `prompts/` | [프롬프트 사용법](../prompts/README.md)부터 따른다. |
| 권한·정책 또는 동작이 불명확함 | 보류 | 담당자에게 확인한 뒤 선택한다. |
