#!/usr/bin/env python3
"""작업대 설치 (WSL2 우분투·리눅스·macOS용). 기본은 미리보기이고 --apply일 때만 쓴다.

하는 일
  1. 묶음의 reference/ 를 --target 폴더로 복사한다(bench 도구·시험·역할 지시문·정책 예시·스킬 링크 스크립트).
  2. --target 안에 policy.yaml(정책 예시 사본), mailbox/, worktrees/ 를 만든다.
  3. --target/workbench/bench.yaml 을 쓴다(JSON 문법. bench와 Herdr mod가 둘 다 읽는다).
  4. --apply 뒤에는 설치한 폴더에서 bench 시험을 돌려 결과를 보인다(--no-test로 끈다).

하지 않는 일
  ~/.claude, ~/.codex, 셸 프로필, Herdr 설정(~/.config/herdr-app)을 읽거나 바꾸지 않는다.
  API 키·로그인 정보를 읽지 않는다. 이미 있는 --target 폴더에는 쓰지 않는다.

사용
  python3 setup.py --target ~/workbench --hub ~/work --space-id <Herdr 스페이스 id>          # 미리보기
  python3 setup.py --target ~/workbench --hub ~/work --space-id <Herdr 스페이스 id> --apply  # 적용
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

BUNDLE = Path(__file__).resolve().parents[1]
REFERENCE = BUNDLE / 'reference'
PERSONAL_DIRS = ['~/.claude', '~/.codex', '~/.config/herdr-app', '~/.bashrc', '~/.zshrc', '~/.profile']


def which(name):
    found = shutil.which(name)
    return str(Path(found).resolve()) if found else None


def version(path, *args):
    if not path:
        return None
    try:
        out = subprocess.run([path, *args], capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def codex_native(codex_cmd):
    """npm 전역 설치의 `codex`는 node 스크립트다. bench는 그 아래 플랫폼 패키지의 실제 실행 파일을 대조에 쓴다."""
    if not codex_cmd:
        return None
    package = Path(codex_cmd).resolve()
    for _ in range(4):
        package = package.parent
        if (package / 'package.json').is_file() and package.name == 'codex':
            break
    else:
        return None
    hits = [p for p in package.glob('node_modules/@openai/codex-*/vendor/*/bin/codex') if os.access(p, os.X_OK)]
    hits += [p for p in package.glob('node_modules/@openai/codex-*/vendor/*/codex/codex') if os.access(p, os.X_OK)]
    return str(hits[0].resolve()) if len(hits) == 1 else None


def plan(args):
    target = Path(args.target).expanduser().resolve()
    hub = Path(args.hub).expanduser().resolve()
    tools = {
        'python3': sys.executable,
        'hc': args.hc or which('hc'),
        'claude': args.claude or which('claude'),
        'codex': args.codex or which('codex'),
        'git': which('git'),
    }
    codex_process = args.codex_process or codex_native(tools['codex'])
    config = {
        'space_id': args.space_id,
        'space_name': args.space_name,
        'mailbox': str(target / 'mailbox'),
        'roles': str(target / 'roles'),
        'cwd': str(hub),
        'worktrees': str(target / 'worktrees'),
        'hc': tools['hc'] or '<채울 것: hc 경로>',
        'link_repo_skills': str(target / 'harness' / 'link-repo-skills.sh'),
        'policy': str(target / 'policy.yaml'),
        'vendors': {
            'claude': {'executable': tools['claude'] or '<채울 것: claude 경로>', 'model': args.claude_model},
            'codex': {'executable': tools['codex'] or '<채울 것: codex 경로>', 'model': args.codex_model,
                      'process_executable': codex_process or '<채울 것: codex 실제 실행 파일 경로>'},
        },
    }
    if args.herdr_app:
        config['herdr_app'] = args.herdr_app
    files = sorted(str(p.relative_to(REFERENCE)) for p in REFERENCE.rglob('*')
                   if p.is_file() and '__pycache__' not in p.parts)
    return target, hub, tools, codex_process, config, files


def check_python():
    problems = []
    if sys.version_info < (3, 9):
        problems.append(f'Python 3.9 이상이 필요하다(지금 {sys.version.split()[0]}). bench는 zoneinfo를 쓴다')
    try:
        import yaml  # noqa: F401
    except ImportError:
        problems.append('PyYAML이 없다. bench close가 정책 파일을 PyYAML로 읽는다. 우분투: sudo apt install python3-yaml')
    return problems


def show(target, hub, tools, codex_process, config, files, args):
    print('== 작업대 설치 미리보기' if not args.apply else '== 작업대 설치 적용')
    print(f'묶음:   {BUNDLE}')
    print(f'설치:   {target}  ({"이미 있음, 쓰지 않는다" if target.exists() else "새로 만든다"})')
    print(f'허브:   {hub}  ({"있음" if hub.is_dir() else "없음, 디렉터가 일할 폴더다. 먼저 만든다"})')
    print('\n도구')
    for name, path in tools.items():
        shown = version(path, '--version') if name != 'python3' else sys.version.split()[0]
        print(f'  {name:8} {path or "없음"}  {shown or ""}')
    print(f'  codex 실제 실행 파일: {codex_process or "찾지 못함. --codex-process로 넣는다"}')
    print('\n만들 파일')
    print(f'  {target}/ 아래 reference 사본 {len(files)}개 (workbench/·roles/·harness/·mods/·LICENSES/ 등)')
    print(f'  {target}/policy.yaml (policy.example.yaml 사본)')
    print(f'  {target}/mailbox/, {target}/worktrees/ (빈 폴더)')
    print(f'  {target}/workbench/bench.yaml:')
    print('    ' + json.dumps(config, ensure_ascii=False, indent=2).replace('\n', '\n    '))
    print('\n바꾸지 않는 곳')
    print('  ' + ', '.join(PERSONAL_DIRS) + ' (읽지도 않는다)')


def apply(target, config, args):
    if target.exists():
        raise SystemExit(f'중단: {target}가 이미 있다. 다른 --target을 고르거나 직접 확인한다.')
    shutil.copytree(REFERENCE, target, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(target / 'policy.example.yaml', target / 'policy.yaml')
    (target / 'mailbox').mkdir()
    (target / 'worktrees').mkdir()
    (target / 'harness' / 'link-repo-skills.sh').chmod(0o755)
    (target / 'workbench' / 'bench.yaml').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    print(f'\n썼다: {target}')
    if args.no_test:
        return 0
    print('\n== 설치한 폴더에서 bench 시험')
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py'],
                            cwd=target / 'workbench', capture_output=True, text=True)
    tail = (result.stdout + result.stderr).strip().splitlines()[-12:]
    print('\n'.join(tail))
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--target', required=True, help='작업대를 설치할 새 폴더 (예: ~/workbench)')
    parser.add_argument('--hub', required=True, help='디렉터가 일할 폴더 (레포들을 두는 곳, 예: ~/work)')
    parser.add_argument('--space-id', required=True, help='Herdr 스페이스 id. 그 머신에서 쓰는 id(앞의 "<머신>/" 접두를 뗀 값)')
    parser.add_argument('--space-name', default='workbench')
    parser.add_argument('--hc'), parser.add_argument('--claude'), parser.add_argument('--codex')
    parser.add_argument('--codex-process', help='Codex 실제 실행 파일 경로 (자동으로 못 찾을 때)')
    parser.add_argument('--herdr-app', help='Herdr 앱 명령 경로. WSL 안에서는 비워 둔다')
    parser.add_argument('--claude-model', default='claude-opus-5-5')
    parser.add_argument('--codex-model', default='gpt-6.1-sol')
    parser.add_argument('--apply', action='store_true', help='미리보기 대신 실제로 쓴다')
    parser.add_argument('--no-test', action='store_true')
    args = parser.parse_args()

    problems = check_python()
    target, hub, tools, codex_process, config, files = plan(args)
    show(target, hub, tools, codex_process, config, files, args)
    if problems:
        print('\n먼저 고칠 것')
        for p in problems:
            print('  - ' + p)
    if not args.apply:
        print('\n미리보기만 했다. 내용이 맞으면 같은 명령에 --apply를 붙인다.')
        return 0
    if problems:
        raise SystemExit('중단: 위 "먼저 고칠 것"을 고친 뒤 다시 실행한다.')
    return apply(target, config, args)


if __name__ == '__main__':
    sys.exit(main())
