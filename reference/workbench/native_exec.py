#!/usr/bin/env python3
"""Witness the scrubbed actual PTY environment, then exec an allowlisted native CLI."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile




def native_environment(source):
    # Keep the inherited login/home/locale/path and every other variable; remove only API keys.
    child = dict(source)
    child.pop('ANTHROPIC_API_KEY', None)
    child.pop('OPENAI_API_KEY', None)
    child['TERM'] = 'xterm-256color'
    child['COLORTERM'] = 'truecolor'
    # LANG, LC_*, HOME and PATH retain their exact inherited values, including absence.
    return child


def record_and_exec(argv, directory, allowed, codex=()):
    if not argv or argv[0] not in allowed:
        raise ValueError('Native executable is not allowlisted')
    identity = os.environ.get('HC_TERMINAL_ID', '')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', identity) or identity in ('.', '..'):
        raise ValueError('Missing or invalid actual terminal identity')
    try:
        tty = os.ttyname(0)
    except OSError:
        tty = None
    child_env = native_environment(os.environ)
    anthropic_present = 'ANTHROPIC_API_KEY' in child_env
    openai_present = 'OPENAI_API_KEY' in child_env
    evidence = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'address': identity, 'pid': os.getpid(), 'tty': tty,
        'native_executable': argv[0],
        'anthropic_api_key_present': anthropic_present,
        'openai_api_key_present': openai_present,
        'keys_removed': not anthropic_present and not openai_present,
        'terminal_environment': {
            'TERM': child_env['TERM'], 'COLORTERM': child_env['COLORTERM'],
            'LANG_present': 'LANG' in child_env,
            'locale_variable_names': sorted(k for k in child_env if k.startswith('LC_')),
            'HOME_present': 'HOME' in child_env, 'PATH_present': 'PATH' in child_env,
            'NO_COLOR_present': 'NO_COLOR' in child_env,
        },
    }
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ('native-' + identity + '.json')
    fd, temporary = tempfile.mkstemp(prefix='.native-', dir=directory)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(evidence, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if not evidence['keys_removed']:
        raise ValueError('Refusing native launch: API key environment scrub failed')
    if argv[0] in codex:
        # Codex hands its shell tool only a core environment (shell_environment_policy.inherit = "core"),
        # so bench CLI calls from a Codex shell saw no HC_TERMINAL_ID (11/11, t4c·t4d). Pass this
        # terminal's own validated identity to that shell; nothing else from the environment is widened.
        argv = [argv[0], '-c', f'shell_environment_policy.set.HC_TERMINAL_ID="{identity}"', *argv[1:]]
    os.execve(argv[0], argv, child_env)


def main():
    try:
        from bench import load_config
        if len(sys.argv) < 4 or sys.argv[1] != '--config':
            raise ValueError('Expected --config PATH EXECUTABLE')
        config = load_config(sys.argv[2])
        record_and_exec(sys.argv[3:], Path(config['mailbox']) / 'evidence',
                        {v['executable'] for v in config['vendors'].values()},
                        codex={config['vendors']['codex']['executable']} if 'codex' in config['vendors'] else set())
    except (ValueError, OSError) as error:
        # Error text never includes environment values or native output.
        if isinstance(error, OSError):
            print('Native exec failed; inspect scoped environment witness', file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
