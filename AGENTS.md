# 이 레포에서 일하는 에이전트에게

이 레포는 Herdr 작업 환경을 다른 사람에게 공유하는 자료다. 이 폴더에서 열린 에이전트는 다음을 지킨다.

- [docs/03-safety-rules.md](docs/03-safety-rules.md)를 세션 내내 지킨다. 로그인 정보·API 키·토큰을 읽거나 출력하지 않고, 승인 창은 사람이 답한다. 예외는 사람이 START-WITH-CODEX.md 4-3에 따라 켠 Codex 자동 승인 검토뿐이다.
- 이 레포에 원래 있던 파일은 고치지 않고 push하지 않는다. 받는 사람의 기록과 초안은 `my-setup/`(Codex 안내)이나 `setup-notes.md`·`port/`(Claude 안내)에 만든다. 이 경로는 `.gitignore`에 있다. 작업대 설치 폴더는 이 레포 밖에 둔다(윈도우 직접 이식의 `port/`만 예외).
- 사람이 킥오프, 인터뷰, 환경 구축을 요청하면 [START-WITH-CODEX.md](START-WITH-CODEX.md)를 따른다. Claude Code로 원본과 같은 작업대를 세울 때는 [SETUP-WITH-CLAUDE.md](SETUP-WITH-CLAUDE.md)를 따른다.
- 문서와 명령 출력에 없는 사실은 '확인 필요'로 적는다.
