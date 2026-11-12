# 에이전트 작업대 설치 안내

이 묶음은 Windows에서 Claude Code와 Codex를 사용하는 사람이 Herdr 작업대를 구성하도록 돕는다. 작업대는 여러 에이전트의 세션과 보고를 계층으로 관리한다. 완성된 Windows 설치본이 아니라 확인과 이식이 필요한 자료다.

가장 쉬운 길은 [SETUP-WITH-CLAUDE.md](SETUP-WITH-CLAUDE.md)다. Herdr를 설치한 뒤 Herdr 터미널에서 Claude Code를 열고, 그 파일의 프롬프트를 차례로 붙여 넣으면 Claude가 운영체제를 확인하고 아래 자료를 골라 쓴다. macOS, 윈도우 + WSL2, 윈도우 직접을 모두 다룬다.

경로별 자료를 직접 따라가려면 먼저 [PC 점검표](docs/00-checklist.md)를 확인하고 설치 경로를 고른다. WSL2를 사용할 수 있으면 `wsl2/`의 안내를 따른다. 사용할 수 없으면 `prompts/`에서 Claude Code에 단계별 지시를 주어 Windows에 맞게 구성한다. 각 경로의 자료가 없으면 준비될 때까지 멈춘다.

- `docs/`: 사전 점검, 구성 설명, 플랫폼 차이와 안전 규칙
- `reference/`: 이식할 원본 코드, mod, 역할 지시문과 정책 예시
- `wsl2/`: WSL2 경로 안내
- `prompts/`: Windows에서 직접 이식하는 단계별 프롬프트

로그인 정보는 복사하지 않고 승인 창은 사람이 직접 처리한다. 자세한 내용은 [안전 규칙](docs/03-safety-rules.md)을 따른다.
