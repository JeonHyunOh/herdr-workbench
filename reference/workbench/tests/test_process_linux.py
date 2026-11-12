"""B28 (2026-11-12, t6f G8): MCP identity recovery must match the Codex ancestor on Linux too.

Linux `ps -o comm=` gives only the executable's name ('codex'), so the comparison with the configured
full path never matched there. On Linux the executable is read from /proc/<pid>/exe; where there is no
/proc (macOS) ps's full path is used exactly as before. The fallback only runs when MCP did not receive
HC_TERMINAL_ID; a mismatch refuses the identity, it never grants one.
"""
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import test_bench

LSTART = 'Wed Nov  4 23:37:21 2026'
LINUX_CODEX = '/usr/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex'
MAC_CODEX = '/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex'


def fake_ps(table):
    """pid -> (ppid, comm): what /bin/ps prints for that pid, nothing for an unknown one."""
    def run(args, **kwargs):
        pid = int(args[args.index('-p') + 1])
        if pid not in table:
            return subprocess.CompletedProcess(args, 1, '', '')
        ppid, comm = table[pid]
        return subprocess.CompletedProcess(args, 0, f'{pid} {ppid} {LSTART} {comm}\n', '')
    return run


class LinuxExecutable(unittest.TestCase):
    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.proc = self.root / 'proc'
        self.proc.mkdir()

    def link(self, pid, target):
        (self.proc / str(pid)).mkdir()
        os.symlink(target, self.proc / str(pid) / 'exe')

    def test_linux_reads_the_full_path_from_proc(self):
        self.link(4100, LINUX_CODEX)
        with patch.object(self.module.subprocess, 'run', side_effect=fake_ps({4100: (4000, 'codex')})):
            info = self.module.process_metadata(4100, proc_root=self.proc)
        self.assertEqual((info['executable'], info['executable_source']), (LINUX_CODEX, 'proc'))
        self.assertEqual((info['pid'], info['ppid']), (4100, 4000))

    def test_macos_without_proc_keeps_the_ps_path(self):
        with patch.object(self.module.subprocess, 'run', side_effect=fake_ps({4100: (4000, MAC_CODEX)})) as ps:
            info = self.module.process_metadata(4100, proc_root=self.root / 'no-proc')
        self.assertEqual((info['executable'], info['executable_source']), (MAC_CODEX, 'ps'))
        self.assertEqual(ps.call_args.args[0], ['/bin/ps', '-o', 'pid=,ppid=,lstart=,comm=', '-p', '4100'])

    def test_linux_without_a_readable_link_falls_back_to_ps(self):
        with patch.object(self.module.subprocess, 'run', side_effect=fake_ps({4100: (4000, 'codex')})):
            info = self.module.process_metadata(4100, proc_root=self.proc)
        self.assertEqual((info['executable'], info['executable_source']), ('codex', 'ps'))


class LinuxIdentity(unittest.TestCase):
    """End to end: the helper (4300) under python (4200) under Codex (4100), read through process_metadata."""
    spawn = test_bench.HostContract.spawn
    hierarchy = test_bench.HostContract.hierarchy

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.hierarchy()
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        started = datetime.strptime(LSTART, '%a %b %d %H:%M:%S %Y').astimezone()
        witness = {'timestamp': (started + timedelta(milliseconds=20)).isoformat(), 'address': 't103', 'pid': 4100,
                   'native_executable': self.host.config['vendors']['codex']['executable'],
                   'anthropic_api_key_present': False, 'openai_api_key_present': False, 'keys_removed': True}
        evidence = self.root / 'mailbox' / 'evidence'
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / 'native-t103.json').write_text(json.dumps(witness))

    def resolve(self, ps_table, links):
        for pid, target in links.items():
            (self.proc / str(pid)).mkdir()
            os.symlink(target, self.proc / str(pid) / 'exe')
        with patch.object(self.module.subprocess, 'run', side_effect=fake_ps(ps_table)):
            return self.host.resolve_mcp_identity(
                None, process_info=lambda pid: self.module.process_metadata(pid, proc_root=self.proc), starting_pid=4300)

    def test_linux_resolves_the_registered_codex_ancestor(self):
        self.host.config['vendors']['codex']['process_executable'] = LINUX_CODEX
        table = {4300: (4200, 'python3'), 4200: (4100, 'python3'), 4100: (4000, 'codex'), 4000: (1, 'bash')}
        links = {4300: '/usr/bin/python3.12', 4200: '/usr/bin/python3.12', 4100: LINUX_CODEX, 4000: '/usr/bin/bash'}
        self.assertEqual(self.resolve(table, links), 't103')

    def test_linux_configured_path_through_a_symlink_still_matches(self):
        real = self.root / 'codex-real'
        real.write_text('')
        alias = self.root / 'codex-alias'
        alias.symlink_to(real)
        self.host.config['vendors']['codex']['process_executable'] = str(alias)
        table = {4300: (4200, 'python3'), 4200: (4100, 'python3'), 4100: (4000, 'codex')}
        self.assertEqual(self.resolve(table, {4100: os.path.realpath(real)}), 't103')

    def test_linux_other_executable_is_still_refused(self):
        self.host.config['vendors']['codex']['process_executable'] = LINUX_CODEX
        table = {4300: (4200, 'python3'), 4200: (4100, 'python3'), 4100: (4000, 'codex')}
        with self.assertRaises(ValueError):
            self.resolve(table, {4100: '/tmp/not-codex'})

    def test_macos_comparison_is_unchanged(self):
        self.host.config['vendors']['codex']['process_executable'] = MAC_CODEX
        table = {4300: (4200, '/opt/homebrew/bin/python3'), 4200: (4100, '/opt/homebrew/bin/python3'), 4100: (4000, MAC_CODEX)}
        self.assertEqual(self.resolve(table, {}), 't103')
        # macOS compares ps's path exactly: a configured symlink is not resolved there (as before B28).
        real = self.root / 'codex-real'
        real.write_text('')
        alias = self.root / 'codex-alias'
        alias.symlink_to(real)
        self.host.config['vendors']['codex']['process_executable'] = str(alias)
        table[4100] = (4000, os.path.realpath(real))
        with self.assertRaises(ValueError):
            self.resolve(table, {})


if __name__ == '__main__':
    unittest.main()
