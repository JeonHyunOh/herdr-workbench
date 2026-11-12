# P3. bench 설정

목적: 실행에 필요한 경로와 스페이스 id를 확인해 설정한다.

## 붙여 넣을 프롬프트

```text
docs/03-safety-rules.md를 지킨다. P1의 확인 결과와 이식한 bench의 설정 형식을 바탕으로 작업 폴더에 둘 bench.yaml의 초안을 만든다. PORT/notes.md를 먼저 읽는다. 키는 다음을 모두 넣는다. `space_id`(Herdr 스페이스 id), `space_name`, `mailbox`(PORT/mailbox), `roles`(PORT/roles), `cwd`(디렉터가 일할 폴더, 사람에게 확인), `worktrees`(PORT/worktrees), `hc`, `link_repo_skills`(B10 결과의 스크립트 경로), `policy`(PORT/policy.yaml, policy.example.yaml 사본), `vendors.claude.executable`·`vendors.claude.model`, `vendors.codex.executable`·`vendors.codex.model`·`vendors.codex.process_executable`, 그리고 P2 B4에서 정한 Python 실행 파일 키. `herdr_app`은 선택이다. 형식 예는 묶음의 wsl2/setup.py가 만드는 config 사전이다. 파일은 JSON 문법으로 쓴다(bench와 Herdr mod가 둘 다 읽는다). docs/02-platform-points.md의 B13에 따라 Codex 명령 래퍼가 아닌 실제 실행 파일 경로도 확인해 넣는다. 확인하지 못한 값은 지어내지 말고 '확인 필요'로 표시한다. 경로와 파일 전체 내용을 먼저 화면에 보여 주고 저장하지 않은 채 사람의 확인을 기다린다. 사람이 확인한 뒤에만 작업 폴더의 bench.yaml을 저장한다. 사람 설정 파일은 직접 수정하지 않는다.
```

## 확인할 결과

파일 경로와 전체 설정 초안이 보이고, 모든 경로가 이 PC에서 확인한 값인지 사람이 살핀다. 특히 스페이스 id와 Codex 실제 실행 파일 경로를 구분한다. 확인 전에는 파일이 저장되지 않아야 한다.

## 멈출 때

필수 경로나 스페이스 id를 확인하지 못했거나 사람이 초안을 확인하지 않았다면 저장하지 않고 멈춘다.
