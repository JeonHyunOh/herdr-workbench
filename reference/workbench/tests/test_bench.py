import subprocess
import errno
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
import sys
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / 'bench.py'

def write_config(root):
    config = {
      'space_id': 'test-space', 'space_name': 'test-workbench',
      'mailbox': str(root / 'mailbox'), 'roles': str(root / 'roles'),
      'cwd': str(root / 'fixture'), 'worktrees': str(root / 'worktrees'),
      'hc': '/home/you/.local/bin/hc',
      'link_repo_skills': str(HELPER.parent.parent / 'harness/link-repo-skills.sh'),
      'policy': str(HELPER.parent.parent / 'policy.example.yaml'),
      'vendors': {
        'claude': {'executable': '/home/you/.local/bin/claude', 'model': 'claude-opus-5-5'},
        'codex': {'executable': '/opt/homebrew/bin/codex', 'model': 'gpt-6.1-sol',
          'process_executable': '/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex'}
      }
    }
    path = root / 'bench.yaml'
    path.write_text(json.dumps(config))
    return path

class CliContract(unittest.TestCase):
    def test_arbitrary_cwd_and_target_cli_arguments_are_rejected(self):
        for tail in [['spawn', '--role', 'worker-review', '--unknown', '/tmp'],
                     ['report', '--summary', 'x', '--to', 'foreign']]:
            result = subprocess.run([sys.executable, str(HELPER)] + tail, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('unrecognized arguments', result.stderr)

    def test_help_does_not_launch_or_require_identity(self):
        result = subprocess.run([sys.executable, str(HELPER), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('spawn', result.stdout)

    def test_spawn_cli_exposes_name_display_and_resume(self):
        result = subprocess.run([sys.executable, str(HELPER), 'spawn', '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for flag in ('--name', '--display', '--resume'):
            self.assertIn(flag, result.stdout)

class HostContract(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('v3_session', HELPER)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.assertTrue(hasattr(self.module, 'SessionHost'), 'Durable scoped session host is missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'fixture').mkdir()
        (self.root / 'roles').mkdir()
        for role, filename in [('secretary', 'secretary'), ('lead', 'lead'), ('worker-review', 'worker-review')]:
            (self.root / 'roles' / (filename + '.md')).write_text('Read fixture/task.md; role: ' + role)
        self.config = write_config(self.root)
        self.host = self.module.SessionHost(self.config)

    def spawn(self, role, caller, address):
        boundary = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({'address': address}), ''))
        node = self.host.spawn(role, caller, run=boundary)
        return node, boundary.call_args.args[0]

    def hierarchy(self):
        self.spawn('secretary', 'operator-t4', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')

    def test_spawn_rejects_wrong_parent_duplicate_and_unknown_roles(self):
        with self.assertRaises(ValueError): self.host.spawn('worker-review', 'operator-t4')
        self.spawn('secretary', 'operator-t4', 't101')
        with self.assertRaises(ValueError): self.host.spawn('secretary', 'operator-t4')
        with self.assertRaises(ValueError): self.host.spawn('worker-review', 't101')
        with self.assertRaises(ValueError): self.host.spawn('../../arbitrary', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')
        nodes = self.host.inspect()['nodes']
        self.assertEqual([(n['address'], n['parent'], n['role']) for n in nodes],
                         [('t101', None, 'secretary'), ('t102', 't101', 'lead'), ('t103', 't102', 'worker-review')])
        state = json.loads((self.root / 'mailbox' / 'state.json').read_text())
        self.assertEqual(state['nodes']['t102']['invocation_caller'], 't101')

    def test_spawn_final_env_scrub_fixed_cwd_and_codex_read_only_contract(self):
        _, secretary = self.spawn('secretary', 'operator-t4', 't101')
        self.assertEqual(secretary[0], '/home/you/.local/bin/hc')
        self.assertIn('--no-parent', secretary)
        self.assertEqual(secretary[secretary.index('--cwd') + 1], str(self.root / 'fixture'))
        self.assertIn('herdr.space=test-space', secretary)
        self.assertNotIn('herdr.space=v3-spike', secretary)
        self.assertNotIn('herdr.tab=v3-secretary', secretary)
        native = secretary[secretary.index('--') + 1:]
        self.assertEqual(native[:5] + [native[6], native[7], native[10]], ['/usr/bin/env', '-u', 'ANTHROPIC_API_KEY', '-u', 'OPENAI_API_KEY', 'python3', str(HELPER.parent / 'native_exec.py'), '/home/you/.local/bin/claude'])
        self.assertEqual(native[native.index('--model') + 1], 'claude-opus-5-5')
        self.assertNotIn('--tools', native)
        _, lead = self.spawn('lead', 't101', 't102')
        self.assertEqual(lead[lead.index('--model') + 1], 'claude-opus-5-5')
        _, worker = self.spawn('worker-review', 't102', 't103')
        self.assertEqual(worker[worker.index('--parent') + 1], 't102')
        native = worker[worker.index('--') + 1:]
        self.assertEqual(native[:5] + [native[6], native[7], native[10]], ['/usr/bin/env', '-u', 'ANTHROPIC_API_KEY', '-u', 'OPENAI_API_KEY', 'python3', str(HELPER.parent / 'native_exec.py'), '/opt/homebrew/bin/codex'])
        self.assertIn('--no-daemon', native)
        self.assertEqual(native[native.index('--sandbox') + 1], 'read-only')
        self.assertIn('forced_login_method="chatgpt"', native)
        self.assertTrue(any('mcp_servers.bench.command=' in arg for arg in native))
        self.assertIn('mcp_servers.bench.env_vars=[\"HC_TERMINAL_ID\"]', native)
        self.assertTrue(any('mcp_servers.bench.args=' in arg and 'mcp' in arg for arg in native))
        self.assertFalse(any('HOME=' in arg or 'dangerously' in arg for arg in native))

    def test_multiple_leads_and_same_role_workers_have_unique_native_names(self):
        live_names = set()
        def hc(command, **kwargs):
            name = command[command.index('--name') + 1]
            if name in live_names:
                return subprocess.CompletedProcess(command, 1, '', '{"error":{"kind":"name_taken"}}')
            live_names.add(name)
            native = command[command.index('--') + 1:]
            if '--name' in native:
                self.assertEqual(native[native.index('--name') + 1], name)
            return subprocess.CompletedProcess(command, 0, json.dumps({'address': f't{len(live_names)}'}), '')
        for role, parent in [('secretary', None), ('lead', 't1'), ('lead', 't1'),
                             ('worker-review', 't2'), ('worker-review', 't2')]:
            node = self.host.spawn(role, parent, run=hc)
            self.assertIn(node['name'], live_names)
        self.assertEqual(len(live_names), 5)

    def test_custom_native_name_and_display_label_reach_hc_claude_and_node(self):
        boundary = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({'address': 't101'}), ''))
        node = self.host.spawn('secretary', 'operator-t4', run=boundary, name='director1', display='디렉터')
        command = boundary.call_args.args[0]
        self.assertEqual(command[command.index('--name') + 1], 'director1')
        self.assertIn('bench.display=디렉터', command)
        native = command[command.index('--') + 1:]
        self.assertEqual(native[native.index('--name') + 1], '디렉터')
        self.assertEqual((node['name'], node['display']), ('director1', '디렉터'))
        self.assertEqual(self.host.inspect()['nodes'][0]['display'], '디렉터')

    def test_custom_name_and_display_reject_values_herdr_cannot_hold(self):
        for name in ['디렉터', 'Director1', 'a' * 33, '', 'bad name']:
            with self.assertRaises(ValueError):
                self.host.spawn('secretary', 'operator-t4', dry_run=True, name=name)
        for display in ['', 'x' * 33, 'line\nbreak']:
            with self.assertRaises(ValueError):
                self.host.spawn('secretary', 'operator-t4', dry_run=True, display=display)

    def test_lead_resume_reopens_existing_claude_session_with_role_prompt(self):
        self.spawn('secretary', 'operator-t4', 't101')
        session = '00000000-0000-4000-8000-000000000001'
        boundary = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({'address': 't102'}), ''))
        node = self.host.spawn('lead', 't101', run=boundary, resume=session, task='이어서 진행')
        command = boundary.call_args.args[0]
        native = command[command.index('--') + 1:]
        self.assertEqual(native[native.index('--resume') + 1], session)
        self.assertTrue(native[-1].startswith('Read and follow'), native[-1][:40])
        self.assertIn('이어서 진행', native[-1])
        self.assertEqual(node['resumed_session'], session)

    def test_resume_is_claude_only_needs_session_uuid_and_no_new_worktree(self):
        self.spawn('secretary', 'operator-t4', 't101')
        self.spawn('lead', 't101', 't102')
        session = '00000000-0000-4000-8000-000000000001'
        with self.assertRaises(ValueError):
            self.host.spawn('worker-review', 't102', dry_run=True, resume=session)
        for bad in ['latest', 'a327d165; rm -rf ~', '../00000000-0000-4000-8000-000000000001']:
            with self.assertRaises(ValueError):
                self.host.spawn('lead', 't101', dry_run=True, resume=bad)
        with self.assertRaises(ValueError):
            self.host.spawn('lead', 't101', dry_run=True, resume=session, worktree=(str(self.root), 'x'))

    def test_report_is_durable_before_projection_notification(self):
        self.hierarchy()
        observed = []
        def notify(report):
            disk = json.loads((self.root / 'mailbox' / 'state.json').read_text())
            view = json.loads((self.root / 'mailbox' / 'view.json').read_text())
            observed.append((report['report_id'] in disk['reports'], view['nodes'][1]['unread_count']))
        report = self.host.report('t103', 'Read task successfully', True, report_id='worker-result-1', notify=notify)
        self.assertEqual((report['from'], report['to']), ('t103', 't102'))
        self.assertEqual(observed, [(True, 1)])
        self.assertTrue(self.host.inspect()['nodes'][2]['complete'])

    def test_wait_held_gate_returns_pending_reports_count_and_ids_without_ack(self):
        self.hierarchy()
        archived = self.host.report('t103', 'old', False, 'old-report')
        self.host.ack('t102', archived['report_id'])
        first = self.host.report('t103', 'progress', False, 'pending-progress')
        second = self.host.report('t103', 'finished', True, 'pending-complete')
        self.host.report('t102', 'for secretary only', False, 'foreign-inbox')
        gate = self.root / 'mailbox' / 'release-lead'
        state_before = (self.root / 'mailbox' / 'state.json').read_bytes()
        held = self.host.wait('t102', timeout=0, release_file=str(gate))
        self.assertEqual(held['status'], 'timeout')
        self.assertFalse(held['gate_released'])
        self.assertEqual(held['reports'], [first, second])
        self.assertEqual(held['pending_report_count'], 2)
        self.assertEqual(held['pending_report_ids'], ['pending-progress', 'pending-complete'])
        self.assertFalse(gate.exists())
        self.assertEqual((self.root / 'mailbox' / 'state.json').read_bytes(), state_before)
        gate.touch()
        ready = self.host.wait('t102', timeout=0, release_file=str(gate))
        self.assertEqual(ready['status'], 'ready')
        self.assertTrue(ready['gate_released'])
        self.assertEqual(ready['reports'], [first, second])
        self.assertEqual(ready['pending_report_count'], 2)
        self.assertEqual(ready['pending_report_ids'], held['pending_report_ids'])

    def test_wait_empty_timeout_and_ungated_ready_have_explicit_pending_summary(self):
        self.hierarchy()
        empty = self.host.wait('t102', timeout=0)
        self.assertEqual(empty['status'], 'timeout')
        self.assertTrue(empty['gate_released'])
        self.assertEqual(empty['reports'], [])
        self.assertEqual(empty['pending_report_count'], 0)
        self.assertEqual(empty['pending_report_ids'], [])
        report = self.host.report('t103', 'complete', True)
        ready = self.host.wait('t102', timeout=0)
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(ready['reports'], [report])
        self.assertEqual(ready['pending_report_count'], 1)
        self.assertEqual(ready['pending_report_ids'], [report['report_id']])

    def test_inspect_lock_permission_error_explains_write_access_and_worker_mcp(self):
        self.hierarchy()
        lock_path = self.root / 'mailbox' / '.lock'
        before = {p.name: p.read_bytes() for p in (self.root / 'mailbox').glob('*.json')}
        original_open = Path.open
        for code in [errno.EPERM, errno.EACCES]:
            def denied_open(path, *args, **kwargs):
                if path == lock_path:
                    raise PermissionError(code, 'Operation not permitted', str(path))
                return original_open(path, *args, **kwargs)
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(errno=code), patch.object(Path, 'open', denied_open), \
                    patch.object(sys, 'argv', [str(HELPER), '--config', str(self.config), 'inspect']), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as stopped:
                    self.module.main()
            self.assertEqual(stopped.exception.code, 1)
            self.assertEqual(stdout.getvalue(), '')
            message = json.loads(stderr.getvalue())['error']
            self.assertIn(str(lock_path), message)
            self.assertIn('write access', message)
            self.assertIn('sandbox', message)
            self.assertIn('MCP', message)
            self.assertIn('bench_inbox', message)
            self.assertIn('bench_report', message)
        self.assertEqual({p.name: p.read_bytes() for p in (self.root / 'mailbox').glob('*.json')}, before)

    def test_worker_role_prompts_use_mcp_instead_of_cli_inspect(self):
        self.host.config['roles'] = str(HELPER.parents[1] / 'roles')
        for role in ['worker-code', 'worker-review', 'worker-query']:
            with self.subTest(role=role):
                prompt = self.host.argv(role, 't102')[-1]
                self.assertNotIn('python3 "$BENCH" inspect', prompt)
                self.assertIn('작업자는 `inspect` 대신 MCP', prompt)
                self.assertIn('bench_inbox', prompt)
                self.assertIn('bench_report', prompt)

    def test_duplicate_report_retry_is_one_message_and_conflicting_id_rejected(self):
        self.hierarchy()
        first = self.host.report('t103', 'result', True, report_id='stable-1')
        second = self.host.report('t103', 'result', True, report_id='stable-1')
        self.assertEqual(first['report_id'], second['report_id'])
        self.assertEqual(len(self.host.inbox('t102')), 1)
        with self.assertRaises(ValueError): self.host.report('t103', 'different', True, report_id='stable-1')
        auto = self.host.report('t103', 'retry without explicit ID', True)
        self.assertEqual(auto['report_id'], self.host.report('t103', 'retry without explicit ID', True)['report_id'])

    def test_ack_and_archive_never_delete_reports_or_permit_wrong_recipient(self):
        self.hierarchy()
        item = self.host.report('t103', 'result', True)
        with self.assertRaises(ValueError): self.host.ack('t101', item['report_id'])
        self.assertEqual(len(self.host.inbox('t102')), 1)
        self.host.ack('t102', item['report_id'])
        self.assertEqual(self.host.inbox('t102'), [])
        self.assertEqual(self.host.inspect()['nodes'][1]['unread_count'], 0)
        reloaded = self.module.SessionHost(self.config)
        archived = reloaded.inbox('t102', include_archived=True)
        self.assertEqual(archived[0]['summary'], 'result')
        self.assertIsNotNone(archived[0]['acked_at'])
        reloaded.ack('t102', item['report_id'])
        parent = reloaded.report('t102', 'Reviewed child ' + item['report_id'], True)
        self.assertEqual(parent['to'], 't101')
        self.assertEqual(len(reloaded.inbox('t101')), 1)

    def test_unknown_identity_cannot_report_or_read_and_secretary_cannot_report_up(self):
        self.hierarchy()
        for action in [lambda: self.host.report('foreign', 'x', True), lambda: self.host.inbox('foreign'),
                       lambda: self.host.report('t101', 'x', True)]:
            with self.assertRaises(ValueError): action()

    def test_failed_spawn_keeps_failure_evidence_and_no_success_node(self):
        boundary = Mock(return_value=subprocess.CompletedProcess([], 1, '', 'launch failed'))
        with self.assertRaises(RuntimeError): self.host.spawn('secretary', 'operator-t4', run=boundary)
        self.assertEqual(self.host.inspect()['nodes'], [])
        records = list((self.root / 'mailbox' / 'evidence').glob('spawn-*.json'))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text())['returncode'], 1)

    def test_notification_failure_and_corrupt_projection_recover_without_losing_report(self):
        self.hierarchy()
        def fail_notification(report):
            raise RuntimeError('notification unavailable')
        with self.assertRaises(RuntimeError):
            self.host.report('t103', 'durable despite notify error', True, 'notify-retry', notify=fail_notification)
        (self.root / 'mailbox' / 'view.json').write_text('interrupted projection')
        self.assertEqual(self.host.report('t103', 'durable despite notify error', True, 'notify-retry')['report_id'], 'notify-retry')
        self.assertEqual(self.host.inspect()['nodes'][1]['pending_report_ids'], ['notify-retry'])

    def test_concurrent_report_retry_produces_single_durable_message(self):
        self.hierarchy()
        with ThreadPoolExecutor(max_workers=4) as pool:
            result = list(pool.map(lambda _: self.host.report('t103', 'same retry', True, 'concurrent-1'), range(12)))
        self.assertEqual({r['report_id'] for r in result}, {'concurrent-1'})
        self.assertEqual(len(self.host.inbox('t102')), 1)
        self.assertEqual(self.host.inspect()['nodes'][1]['unread_count'], 1)

    def test_unknown_launch_result_blocks_retry_instead_of_creating_second_native_cli(self):
        boundary = Mock(return_value=subprocess.CompletedProcess([], 0, '{"unexpected": true}', ''))
        with self.assertRaises(RuntimeError): self.host.spawn('secretary', 'operator-t4', run=boundary)
        second = Mock(return_value=subprocess.CompletedProcess([], 0, '{"address":"t999"}', ''))
        with self.assertRaises(RuntimeError): self.host.spawn('secretary', 'operator-t4', run=second)
        self.assertEqual(second.call_count, 0)

    def write_native_witness(self, address='t103', pid=4100):
        witness = {'timestamp': '2026-11-04T14:37:21.023626+00:00', 'address': address,
                   'pid': pid, 'tty': '/dev/ttys024', 'native_executable': '/opt/homebrew/bin/codex',
                   'anthropic_api_key_present': False, 'openai_api_key_present': False, 'keys_removed': True}
        directory = self.root / 'mailbox' / 'evidence'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ('native-' + address + '.json')).write_text(json.dumps(witness))

    def test_process_metadata_reads_only_pid_parent_birth_and_executable(self):
        result = subprocess.CompletedProcess([], 0, '14285 30205 Wed Nov  4 23:37:21 2026 /opt/homebrew/bin/codex\n', '')
        with patch.object(self.module.subprocess, 'run', return_value=result) as boundary:
            info = self.module.process_metadata(14285)
        self.assertEqual(info['pid'], 14285)
        self.assertEqual(info['ppid'], 30205)
        self.assertEqual(info['executable'], '/opt/homebrew/bin/codex')
        self.assertEqual(boundary.call_args.args[0], ['/bin/ps', '-o', 'pid=,ppid=,lstart=,comm=', '-p', '14285'])
        self.assertNotIn('args', boundary.call_args.args[0])
        self.assertFalse(boundary.call_args.kwargs['shell'])

    def test_mcp_missing_environment_identity_resolves_only_matching_live_native_ancestor(self):
        self.hierarchy()
        self.write_native_witness()
        processes = {
            4300: {'pid': 4300, 'ppid': 4200, 'started_at': '2026-11-04T14:42:00+00:00', 'executable': '/opt/homebrew/bin/python3'},
            4200: {'pid': 4200, 'ppid': 4100, 'started_at': '2026-11-04T14:42:00+00:00', 'executable': '/opt/homebrew/bin/python3'},
            4100: {'pid': 4100, 'ppid': 4000, 'started_at': '2026-11-04T14:37:21+00:00', 'executable': '/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex'},
            4000: {'pid': 4000, 'ppid': 1, 'started_at': '2026-11-04T14:00:00+00:00', 'executable': '/bin/zsh'}}
        self.assertEqual(self.host.resolve_mcp_identity(None, process_info=processes.get, starting_pid=4300), 't103')
        self.host.report('t103', 'identity recovered through native ancestor', True)
        self.assertEqual(self.host.inbox('t102')[0]['from'], 't103')
        # A nonempty, unknown identity is never silently replaced by process evidence.
        with self.assertRaises(ValueError):
            self.host.resolve_mcp_identity('unregistered', process_info=processes.get, starting_pid=4300)
        # PID reuse after witness creation must not authorize a new process.
        processes[4100]['started_at'] = '2026-11-04T14:40:00+00:00'
        with self.assertRaises(ValueError):
            self.host.resolve_mcp_identity(None, process_info=processes.get, starting_pid=4300)

    def test_mcp_unknown_process_wrong_executable_or_unrelated_witness_is_refused(self):
        self.hierarchy()
        self.write_native_witness()
        wrong = {'pid': 4100, 'ppid': 1, 'started_at': '2026-11-04T14:37:21+00:00', 'executable': '/bin/sh'}
        with self.assertRaises(ValueError):
            self.host.resolve_mcp_identity(None, process_info=lambda pid: wrong if pid == 4100 else None, starting_pid=4100)
        with self.assertRaises(ValueError):
            self.host.resolve_mcp_identity(None, process_info=lambda pid: None, starting_pid=9900)
        self.write_native_witness('unregistered', 4100)
        with self.assertRaises(ValueError):
            self.host.resolve_mcp_identity(None, process_info=lambda pid: None, starting_pid=4100)

    def test_release_gate_cannot_escape_mailbox(self):
        self.hierarchy()
        self.host.report('t103', 'result', True)
        with self.assertRaises(ValueError): self.host.wait('t102', timeout=0, release_file=str(self.root / 'outside'))
        held = self.host.wait('t102', timeout=0, release_file=str(self.root / 'mailbox' / 'release-lead'))
        self.assertEqual(held['status'], 'timeout')
        (self.root / 'mailbox' / 'release-lead').touch()
        self.assertEqual(self.host.wait('t102', timeout=0, release_file=str(self.root / 'mailbox' / 'release-lead'))['status'], 'ready')

    def test_mcp_is_scoped_to_registered_self_and_has_no_spawn_or_arbitrary_target(self):
        self.hierarchy()
        server = self.module.McpServer(self.host, 't103')
        tools = server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})['result']['tools']
        self.assertEqual({t['name'] for t in tools}, {'bench_report', 'bench_inbox', 'bench_ack'})
        result = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'bench_report', 'arguments': {'summary': 'MCP native result', 'complete': True}}})
        self.assertFalse(result['result'].get('isError', False))
        self.assertEqual(self.host.inbox('t102')[0]['summary'], 'MCP native result')
        bad = server.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'bench_report', 'arguments': {'summary': 'x', 'to': 'foreign'}}})
        self.assertTrue(bad['result']['isError'])

    def test_no_task_inspection_spawns_native_hierarchy_without_role_messages(self):
        parent = None
        for role, address in [('secretary','t201'),('lead','t202'),('worker-review','t203')]:
            run = Mock(return_value=subprocess.CompletedProcess([],0,json.dumps({'address':address}),''))
            node = self.host.spawn(role,'operator-root',run=run,no_task=True,parent_override=parent)
            command = run.call_args.args[0]
            self.assertEqual(node['parent'],parent)
            self.assertEqual(node['invocation_caller'],'operator-root')
            self.assertFalse(node['task_provided'])
            self.assertFalse(any('Read fixture/task.md' in arg or 'Read and follow' in arg for arg in command))
            if parent: self.assertEqual(command[command.index('--parent')+1],parent)
            parent = address

    def test_parent_override_requires_same_caller_or_no_task_and_correct_registered_role(self):
        self.spawn('secretary','operator-root','t301')
        with self.assertRaises(ValueError):
            self.host.spawn('lead','operator-root',parent_override='t301')
        with self.assertRaises(ValueError):
            self.host.spawn('worker-review','operator-root',no_task=True,parent_override='t301')
        with self.assertRaises(ValueError):
            self.host.spawn('lead','operator-root',no_task=True,parent_override='foreign')

if __name__ == '__main__':
    unittest.main()
