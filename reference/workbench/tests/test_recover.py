"""B21 (2026-11-11): one command reopens the bench tree after a reboot. Fake hc only; no real terminal ends."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock
import test_bench

SID = '11111111-2222-3333-4444-555555555555'


def shell(role, space='test-space'):
    return {'state': 'live', 'argv': ['/bin/zsh', '-l'], 'foreground': {'name': 'zsh', 'argv': ['/bin/zsh', '-l']},
            'labels': {'herdr.space': space, 'bench.role': role}}


def agent(role):
    return {'state': 'live', 'argv': ['/usr/bin/env'], 'foreground': {'name': '2.1.322', 'argv': ['/Users/x/.local/bin/claude']},
            'labels': {'herdr.space': 'test-space', 'bench.role': role}}


class FakeHc:
    def __init__(self, terminals, next_address='t300', send_starts_agent=True, send_fails=()):
        self.terminals, self.next_address = terminals, next_address
        self.send_starts_agent, self.send_fails, self.calls = send_starts_agent, set(send_fails), []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        verb = args[1]
        if verb == 'get':
            info = self.terminals.get(args[2])
            if info is None:
                return subprocess.CompletedProcess(args, 3, json.dumps({'error': {'kind': 'not_found'}}), '')
            return subprocess.CompletedProcess(args, 0, json.dumps(info), '')
        if verb == 'send':
            if args[2] in self.send_fails:
                return subprocess.CompletedProcess(args, 1, '', 'terminal busy')
            if self.send_starts_agent:
                self.terminals[args[2]] = agent(self.terminals[args[2]]['labels']['bench.role'])
            return subprocess.CompletedProcess(args, 0, '{}', '')
        if verb == 'run':
            address = self.next_address if isinstance(self.next_address, str) else next(self.next_address)
            return subprocess.CompletedProcess(args, 0, json.dumps({'address': address}), '')
        if verb == 'ls':
            return subprocess.CompletedProcess(args, 0, json.dumps({'terminals': []}), '')
        return subprocess.CompletedProcess(args, 0, '{}', '')

    def sent(self):
        return [c[2] for c in self.calls if c[1] == 'send']


class Recover(unittest.TestCase):
    def setUp(self):
        test_bench.HostContract.setUp(self)
        for role in ['worker-code', 'worker-query']:
            (self.root / 'roles' / (role + '.md')).write_text('Fixture worker role')
        def spawn(role, caller, address, **kw):
            return self.host.spawn(role, caller, run=Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({'address': address}), '')), **kw)
        self.spawn_claude_secretary = spawn('secretary', 'operator', 't101')
        spawn('lead', 't101', 't102')
        spawn('worker-code', 't102', 't103', vendor='claude')
        spawn('lead', 't101', 't104', vendor='codex', state_file='/abs/project/lead-state.md')
        spawn('worker-code', 't104', 't105')                      # Codex worker, no state file
        spawn('worker-code', 't102', 't106', vendor='claude')
        spawn('worker-query', 't102', 't107', vendor='claude')
        self.host.park('t102', 't106')                              # stopped on purpose
        with self.host.locked() as state:
            state['nodes']['t107']['closed_at'] = '2026-11-11T12:00:00+00:00'
            self.host.commit(state)
        self.roles = {'t101': 'secretary', 't102': 'lead', 't103': 'worker-code', 't104': 'lead',
                      't105': 'worker-code', 't106': 'worker-code'}

    def state(self):
        return json.loads((self.host.mailbox / 'state.json').read_text())

    def test_spawn_records_the_claude_session_id_and_passes_it(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({'address': 't150'}), ''))
        node = self.host.spawn('worker-code', 't102', run=run, vendor='claude')
        argv = run.call_args_list[0].args[0]
        self.assertEqual(argv[argv.index('--session-id') + 1], node['session_id'])
        run2 = Mock(return_value=subprocess.CompletedProcess([], 0, '{"address":"t151"}', ''))
        resumed = self.host.spawn('worker-code', 't104', vendor='claude', resume=SID, run=run2)
        self.assertEqual(resumed['session_id'], SID)
        self.assertNotIn('--session-id', run2.call_args_list[0].args[0], 'a resumed session keeps its own id')
        self.assertNotIn('session_id', self.state()['nodes']['t105'])   # Codex has no Claude session id

    def test_all_revived_shells_come_back_in_place_top_down(self):
        hc = FakeHc({a: shell(r) for a, r in self.roles.items()})
        plan = self.host.recover('operator', run=hc, dry_run=True)['plan']
        actions = {r['address']: r['action'] for r in plan}
        self.assertEqual(actions, {'t101': 'relaunch', 't102': 'relaunch', 't103': 'relaunch', 't104': 'relaunch',
                                   't105': 'blocked', 't106': 'skip'})
        self.assertEqual(hc.sent(), [], 'dry run sends nothing')
        before = (self.host.mailbox / 'state.json').read_text()
        out = self.host.recover('operator', run=hc, sleep=lambda s: None)
        self.assertEqual(out['status'], 'done')
        self.assertEqual(hc.sent(), ['t101', 't102', 't103', 't104'], 'parents before children')
        text = [c[3] for c in hc.calls if c[1] == 'send'][0]
        self.assertEqual(text, f"exec python3 {self.host.helper} --config {self.host.config_path} relaunch")
        self.assertNotIn('HC_TERMINAL_ID', text)
        self.assertEqual(json.loads(before)['nodes'].keys(), self.state()['nodes'].keys(), 'same addresses, no new records')
        self.assertEqual({r['address'] for r in out['not_reopened']}, {'t105', 't106'})
        self.assertIn('state_file', [r for r in out['not_reopened'] if r['address'] == 't105'][0]['why'])
        self.assertTrue(all(Path(p).is_file() for p in out['backup']['files'].values()))

    def test_all_gone_with_restarted_numbering(self):
        # every terminal is gone; last-alive says t103 had already ended before the outage
        (self.host.mailbox / 'last-alive.json').write_text(json.dumps({'alive': ['t101', 't102', 't104']}))
        hc = FakeHc({}, next_address='t300')
        plan = {r['address']: r for r in self.host.recover('operator', run=hc, dry_run=True)['plan']}
        self.assertEqual(plan['t101']['action'], 'takeover')
        self.assertEqual(plan['t102']['action'], 'recover-child')
        self.assertEqual(plan['t103']['action'], 'skip')
        self.assertIn('before the outage', plan['t103']['why'])
        with self.host.locked() as state:
            state['nodes']['t101']['resumed_session'] = SID
            self.host.commit(state)
        hc.next_address = iter(['t300', 't301', 't302'])
        out = self.host.recover('operator', run=hc, sleep=lambda s: None)
        self.assertEqual(out['status'], 'done', out.get('failed'))
        self.assertEqual(out['done'], [{'address': 't101', 'action': 'takeover', 'new': 't300'},
                                       {'address': 't102', 'action': 'recover-child', 'new': 't301'},
                                       {'address': 't104', 'action': 'recover-child', 'new': 't302'}])
        s = self.state()['nodes']
        self.assertEqual(s['t301']['parent'], 't300')
        self.assertEqual(s['t302']['parent'], 't300')
        self.assertEqual({s[a]['recovery_id'] for a in ('t300', 't301', 't302')}, {out['recovery_id']})
        self.assertEqual(s['t301']['recovered_by'], 'operator')
        self.assertEqual(s['t103']['parent'], 't301', 'the grandchild that had ended stays under the new lead, not reopened')
        runs = [c for c in hc.calls if c[1] == 'run']
        self.assertIn('--resume', runs[1], 'Claude lead keeps its conversation')
        self.assertNotIn('--resume', runs[2])
        self.assertIn('/abs/project/lead-state.md', runs[2][-1], 'Codex lead is told to read its state file')
        # hc restarts numbering and hands out an address bench already knows: refuse, keep the rest
        self.setUp()
        (self.host.mailbox / 'last-alive.json').write_text(json.dumps({'alive': ['t101']}))
        with self.host.locked() as state:
            state['nodes']['t101']['resumed_session'] = SID
            self.host.commit(state)
        out = self.host.recover('operator', run=FakeHc({}, next_address='t107'), sleep=lambda s: None)
        self.assertEqual(out['status'], 'stopped')
        self.assertIn('already in the mailbox', out['failed']['error'])
        self.assertIn('cp ', out['failed']['error'])
        self.assertIsNone(self.state()['nodes']['t101'].get('closed_at'))

    def test_plan_a_refuses_when_any_condition_fails(self):
        (self.host.mailbox / 'last-alive.json').write_text(json.dumps({'alive': ['t101', 't102', 't103', 't104']}))
        with self.host.locked() as state:
            state['nodes']['t101']['resumed_session'] = SID
            self.host.commit(state)
        # 1) an agent still runs somewhere in the tree: children are left to their running parents
        hc = FakeHc({'t104': agent('lead')}, next_address=iter(['t300', 't301']))
        plan = {r['address']: r for r in self.host.recover('operator', run=hc, dry_run=True)['plan']}
        self.assertEqual(plan['t102']['action'], 'decide')
        self.assertIn('another agent in the tree is running', plan['t102']['why'])
        out = self.host.recover('operator', run=hc, sleep=lambda s: None)
        self.assertEqual([d['action'] for d in out['done']], ['takeover'])
        self.assertEqual(len([c for c in hc.calls if c[1] == 'run']), 1, 'no child was reopened')
        # 2) a parent that was not reopened in this recovery: its children are not reopened either
        self.setUp()
        (self.host.mailbox / 'last-alive.json').write_text(json.dumps({'alive': ['t101', 't102', 't103']}))
        with self.host.locked() as state:
            state['nodes']['t101']['resumed_session'] = SID
            for k in ('session_id', 'resumed_session'):
                state['nodes']['t102'].pop(k, None)          # the lead's conversation is unknown -> blocked
            self.host.commit(state)
        hc = FakeHc({}, next_address=iter(['t300', 't301', 't302']))
        out = self.host.recover('operator', run=hc, sleep=lambda s: None)
        why = {r['address']: r['why'] for r in out['not_reopened']}
        self.assertIn('session id', why['t102'])
        self.assertIn('parent was not reopened', why['t103'])
        # 3) takeover with a recovery but without the conditions is refused directly
        self.setUp()
        hc = FakeHc({}, next_address='t300')
        with self.assertRaisesRegex(ValueError, 'whole tree is down'):
            self.host.takeover('operator', 't102', run=hc, recovery={'id': 'r', 'reopened': {'t101'}, 'all_down': False})
        with self.assertRaisesRegex(ValueError, 'parent was reopened'):
            self.host.takeover('operator', 't102', run=hc, recovery={'id': 'r', 'reopened': set(), 'all_down': True})
        with self.assertRaisesRegex(ValueError, 'not a registered workbench session'):
            self.host.takeover('operator', 't102', run=hc)          # outside recover the rule is unchanged
        with self.assertRaisesRegex(ValueError, 'Only the registered parent'):
            self.host.takeover('t104', 't102', run=hc)              # a registered non-parent is refused too
        self.assertEqual([c for c in hc.calls if c[1] == 'run'], [])

    def test_shell_labels_must_match_the_record(self):
        for broken in ({'herdr.space': 'other-space', 'bench.role': 'lead'}, {'herdr.space': 'test-space'}, {}):
            terminals = {a: shell(r) for a, r in self.roles.items()}
            terminals['t102']['labels'] = broken
            hc = FakeHc(terminals)
            out = self.host.recover('operator', run=hc, sleep=lambda s: None)
            self.assertEqual(out['status'], 'refused', broken)
            self.assertEqual(hc.sent(), [], 'nothing is typed into any shell')
        terminals = {a: shell(r) for a, r in self.roles.items()}
        terminals['t102']['name'] = 'someone-else'
        self.assertEqual(self.host.recover('operator', run=FakeHc(terminals), sleep=lambda s: None)['status'], 'refused')

    def test_relaunch_marks_the_recovery(self):
        hc = FakeHc({a: shell(r) for a, r in self.roles.items()})
        out = self.host.recover('operator', run=hc, sleep=lambda s: None)
        s = self.state()['nodes']
        self.assertEqual({s[a]['recovery_id'] for a in ('t101', 't102', 't103', 't104')}, {out['recovery_id']})

    def test_a_different_terminal_on_an_old_address_refuses_everything(self):
        terminals = {a: shell(r) for a, r in self.roles.items()}
        terminals['t101'] = agent('secretary')
        terminals['t102'] = shell('worker-code')            # labels say this is not the lead
        hc = FakeHc(terminals)
        out = self.host.recover('operator', run=hc, sleep=lambda s: None)
        self.assertEqual(out['status'], 'refused')
        self.assertEqual(hc.sent(), [])
        self.assertEqual({r['address']: r['action'] for r in out['plan']}['t101'], 'skip')

    def test_a_failure_stops_and_says_what_is_done_and_left(self):
        hc = FakeHc({a: shell(r) for a, r in self.roles.items()}, send_fails={'t102'})
        out = self.host.recover('operator', run=hc, sleep=lambda s: None)
        self.assertEqual(out['status'], 'stopped')
        self.assertEqual(out['done'], [{'address': 't101', 'action': 'relaunch'}])
        self.assertEqual(out['failed']['address'], 't102')
        self.assertEqual(out['left'], ['t103', 't104'])
        self.assertIn('cp ', out['if_wrong'])
        # an agent that never starts also stops the run
        hc = FakeHc({a: shell(r) for a, r in self.roles.items()}, send_starts_agent=False)
        out = self.host.recover('operator', run=hc, wait_seconds=2, sleep=lambda s: None)
        self.assertEqual(out['status'], 'stopped')
        self.assertIn('did not start', out['failed']['error'])

    def test_relaunch_runs_the_same_program_by_its_own_identity(self):
        captured = []
        self.host.relaunch('t102', exec_fn=lambda path, argv: captured.append(argv))
        argv = captured[0]
        self.assertEqual(argv[0], '/usr/bin/env')
        self.assertEqual(argv[argv.index('--resume') + 1], self.state()['nodes']['t102']['session_id'])
        self.assertIn('[작업대 recover]', argv[-1])
        self.assertFalse(any('HC_TERMINAL_ID=' in a for a in argv))
        self.host.relaunch('t104', exec_fn=lambda path, argv: captured.append(argv))
        self.assertNotIn('--resume', captured[1])
        self.assertIn('/abs/project/lead-state.md', captured[1][-1])
        with self.assertRaisesRegex(ValueError, 'state_file'):
            self.host.relaunch('t105', exec_fn=lambda *a: None)
        with self.assertRaisesRegex(ValueError, 'parked'):
            self.host.relaunch('t106', exec_fn=lambda *a: None)

    def test_last_alive_keeps_running_agents_only(self):
        self.host.note_alive([{'address': 't101', 'state': 'live', 'agent': 'claude-code'},
                              {'address': 't102', 'state': 'live', 'agent': None},
                              {'address': 't103', 'state': 'finished', 'agent': 'claude-code'},
                              {'address': 't107', 'state': 'live', 'agent': 'claude-code'},
                              {'address': 'stranger', 'state': 'live', 'agent': 'claude-code'}])
        saved = json.loads((self.host.mailbox / 'last-alive.json').read_text())
        self.assertEqual(saved['alive'], ['t101'])

    def test_park_and_state_file_are_for_self_or_parent(self):
        with self.assertRaisesRegex(ValueError, 'itself or its registered parent'):
            self.host.park('t101', 't103')
        self.host.park('t102', 't103', reason='끝난 채 둔다')
        self.assertEqual(self.state()['nodes']['t103']['parked_reason'], '끝난 채 둔다')
        self.assertEqual(self.state()['nodes']['t103']['parked_by'], 't102')
        self.host.park('t103', 't103', off=True)
        self.assertNotIn('parked_at', self.state()['nodes']['t103'])
        self.host.set_state_file('t101', '/abs/x.md', target='t104')
        self.assertEqual(self.state()['nodes']['t104']['state_file'], '/abs/x.md')
        with self.assertRaisesRegex(ValueError, 'absolute'):
            self.host.set_state_file('t104', 'relative.md')


if __name__ == '__main__':
    unittest.main()
