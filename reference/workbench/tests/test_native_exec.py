import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

WRAPPER = Path(__file__).resolve().parents[1] / 'native_exec.py'
CLAUDE = '/home/you/.local/bin/claude'
CODEX = '/opt/homebrew/bin/codex'


class NativeExecContract(unittest.TestCase):
    def load_wrapper(self):
        self.assertTrue(WRAPPER.is_file(), 'Actual native child environment witness is missing')
        spec = importlib.util.spec_from_file_location('native_exec', WRAPPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_key_presence_is_removed_but_values_never_written_or_printed(self):
        module = self.load_wrapper()
        child_env = {'HC_TERMINAL_ID': 't-witness', 'HOME': '/home/example', 'PATH': '/bin',
                     'LANG': 'ko_KR.UTF-8', 'LC_CTYPE': 'UTF-8',
                     'ANTHROPIC_API_KEY': 'sensitive-alpha-value', 'OPENAI_API_KEY': 'sensitive-beta-value'}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, child_env, clear=True):
            root = Path(folder).resolve()
            with patch.object(module.os, 'execve', side_effect=RuntimeError('exec intercepted')) as execute:
                with self.assertRaisesRegex(RuntimeError, 'exec intercepted'):
                    module.record_and_exec([CLAUDE, '--model', 'claude-opus-5-5'], root, {CLAUDE, CODEX})
            outgoing = execute.call_args.args[2]
            self.assertNotIn('ANTHROPIC_API_KEY', outgoing)
            self.assertNotIn('OPENAI_API_KEY', outgoing)
            for key in ['HOME', 'PATH', 'LANG', 'LC_CTYPE']:
                self.assertEqual(outgoing[key], child_env[key])
            evidence_file = root / 'native-t-witness.json'
            evidence = json.loads(evidence_file.read_text())
            self.assertFalse(evidence['anthropic_api_key_present'])
            self.assertFalse(evidence['openai_api_key_present'])
            self.assertTrue(evidence['keys_removed'])
            for secret in ['sensitive-alpha-value','sensitive-beta-value','/home/example','ko_KR.UTF-8']:
                self.assertNotIn(secret, evidence_file.read_text())
            self.assertTrue(evidence['terminal_environment']['HOME_present'])
            self.assertTrue(evidence['terminal_environment']['LANG_present'])

    def test_clean_environment_records_pid_tty_then_execs_only_fixed_native(self):
        module = self.load_wrapper()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'HC_TERMINAL_ID': 't-clean'}, clear=True):
            root = Path(folder).resolve()
            with patch.object(module.os, 'ttyname', return_value='/dev/ttys-test'), \
                 patch.object(module.os, 'execve', side_effect=RuntimeError('exec boundary intercepted')) as execv:
                with self.assertRaisesRegex(RuntimeError, 'exec boundary intercepted'):
                    module.record_and_exec([CODEX, '--sandbox', 'read-only'], root, {CLAUDE, CODEX})
            evidence = json.loads((root / 'native-t-clean.json').read_text())
            self.assertEqual(evidence['pid'], os.getpid())
            self.assertEqual(evidence['tty'], '/dev/ttys-test')
            self.assertEqual(evidence['native_executable'], CODEX)
            self.assertTrue(evidence['keys_removed'])
            self.assertFalse(evidence['anthropic_api_key_present'])
            self.assertFalse(evidence['openai_api_key_present'])
            self.assertIn('timestamp', evidence)
            execv.assert_called_once_with(CODEX, [CODEX, '--sandbox', 'read-only'], {'HC_TERMINAL_ID': 't-clean', 'TERM': 'xterm-256color', 'COLORTERM': 'truecolor'})

    def test_non_allowlisted_command_and_unsafe_identity_refused_before_exec(self):
        module = self.load_wrapper()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'HC_TERMINAL_ID': 't-ok'}, clear=True):
            with patch.object(module.os, 'execve') as execv:
                for command in ['/bin/sh', 'claude', '/tmp/claude']:
                    with self.assertRaises(ValueError): module.record_and_exec([command], Path(folder), {CLAUDE, CODEX})
                os.environ['HC_TERMINAL_ID'] = '../../outside'
                with self.assertRaises(ValueError): module.record_and_exec([CLAUDE], Path(folder), {CLAUDE, CODEX})
                self.assertEqual(execv.call_count, 0)



class CodexShellIdentity(unittest.TestCase):
    """11/11 t4c·t4d: a Codex shell must see the terminal's own HC_TERMINAL_ID so bench CLI works."""
    load_wrapper = NativeExecContract.load_wrapper

    def launch(self, argv, identity='t4c'):
        module = self.load_wrapper()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'HC_TERMINAL_ID': identity}, clear=True):
            with patch.object(module.os, 'execve', side_effect=RuntimeError('exec intercepted')) as execute:
                with self.assertRaisesRegex(RuntimeError, 'exec intercepted'):
                    module.record_and_exec(argv, Path(folder), {CLAUDE, CODEX}, codex={CODEX})
        return execute.call_args.args

    def test_codex_gets_its_own_identity_for_the_shell_tool(self):
        path, argv, env = self.launch([CODEX, '--no-daemon', '--model', 'gpt-6.1-sol', 'task text'])
        self.assertEqual(path, CODEX)
        self.assertEqual(argv, [CODEX, '-c', 'shell_environment_policy.set.HC_TERMINAL_ID="t4c"',
                                '--no-daemon', '--model', 'gpt-6.1-sol', 'task text'])
        self.assertEqual(env['HC_TERMINAL_ID'], 't4c')     # the value comes from this terminal, not from bench
        self.assertFalse(any('inherit' in a for a in argv))  # the policy is not widened

    def test_claude_is_unchanged(self):
        _, argv, _ = self.launch([CLAUDE, '--model', 'claude-opus-5-5'])
        self.assertEqual(argv, [CLAUDE, '--model', 'claude-opus-5-5'])

    def test_an_invalid_identity_never_reaches_the_config_override(self):
        module = self.load_wrapper()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'HC_TERMINAL_ID': 't4c" x="1'}, clear=True):
            with patch.object(module.os, 'execve') as execute:
                with self.assertRaisesRegex(ValueError, 'invalid actual terminal identity'):
                    module.record_and_exec([CODEX], Path(folder), {CLAUDE, CODEX}, codex={CODEX})
            execute.assert_not_called()

    def test_main_marks_the_configured_codex_executable(self):
        source = WRAPPER.read_text()
        self.assertIn("codex={config['vendors']['codex']['executable']}", source)

if __name__ == '__main__':
    unittest.main()
