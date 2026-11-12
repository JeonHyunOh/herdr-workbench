"""B1 takeover (2026-11-11): an ended session reopens in a new terminal and keeps its place in the tree."""
import json
from pathlib import Path
import subprocess
import unittest
import test_bench

SID = '11111111-2222-3333-4444-555555555555'


class FakeHc:
    """hc get answers from `states`; hc run hands out `next_address`. Everything else succeeds quietly."""
    def __init__(self, states, next_address='t201'):
        self.states, self.next_address, self.calls = states, next_address, []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if args[1] == 'get':
            state = self.states.get(args[2])
            if state is None:
                return subprocess.CompletedProcess(args, 3, json.dumps({'error': {'kind': 'not_found'}}), '')
            if state == 'hc-down':
                return subprocess.CompletedProcess(args, 1, '', 'connection refused')
            return subprocess.CompletedProcess(args, 0, json.dumps({'state': state}), '')
        if args[1] == 'run':
            return subprocess.CompletedProcess(args, 0, json.dumps({'address': self.next_address}), '')
        return subprocess.CompletedProcess(args, 0, '{}', '')

    def runs(self):
        return [c for c in self.calls if c[1] == 'run']


class Takeover(unittest.TestCase):
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        # director t101 -> lead t102 -> worker t103, the lead was opened from a Claude session
        self.spawn('secretary', 'operator', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')
        with self.host.locked() as state:
            state['nodes']['t102']['resumed_session'] = SID
            state['nodes']['t103']['worktree'] = {'path': '/tmp/wt-103', 'created_by': 't102', 'worktree_created': True}
            self.host.commit(state)
        self.report_to_lead = self.host.report('t103', '[작업자] 끝났다', report_id='r-to-lead')['report_id']
        self.host.report('t102', '[리드] 중간 보고', report_id='r-to-director')

    def nodes(self):
        return self.host.inspect()['nodes'] if isinstance(self.host.inspect(), dict) else None

    def state(self):
        return json.loads((Path(self.host.mailbox) / 'state.json').read_text())

    def test_middle_of_three_levels_is_taken_over(self):
        hc = FakeHc({'t102': 'finished', 't101': 'live', 't103': 'live'})
        out = self.host.takeover('t101', 't102', model='claude-fable-5-1', run=hc)
        self.assertEqual(out['new'], 't201')
        s = self.state()
        new, old = s['nodes']['t201'], s['nodes']['t102']
        # parent and children
        self.assertEqual(new['parent'], 't101')
        self.assertEqual(s['nodes']['t103']['parent'], 't201')
        self.assertEqual(new['role'], 'lead')
        self.assertEqual(new['model'], 'claude-fable-5-1')
        self.assertEqual(new['replaces'], 't102')
        # worktree ownership of the child moves to the new address
        self.assertEqual(s['nodes']['t103']['worktree']['created_by'], 't201')
        # unread report to the old lead is now the new lead's, nothing lost
        self.assertEqual(s['reports'][self.report_to_lead]['to'], 't201')
        self.assertEqual(s['reports'][self.report_to_lead]['original_to'], 't102')
        self.assertEqual([r['report_id'] for r in self.host.inbox('t201')], [self.report_to_lead])
        # the lead's own report to the director is untouched, and the director is told about the takeover
        director = {r['report_id'] for r in self.host.inbox('t101')}
        self.assertIn('r-to-director', director)
        self.assertIn('takeover-t102-t201', director)
        # the old record is closed as replaced and refuses a second takeover
        self.assertEqual(old['close_result']['status'], 'replaced')
        self.assertEqual(old['replaced_by'], 't201')
        with self.assertRaisesRegex(ValueError, 'replaced by t201'):
            self.host.takeover('t101', 't102', run=hc)
        # the new terminal resumes the same Claude conversation with the chosen model
        argv = hc.runs()[0]
        self.assertIn('--resume', argv)
        self.assertEqual(argv[argv.index('--resume') + 1], SID)
        self.assertEqual(argv[argv.index('--model') + 1], 'claude-fable-5-1')
        self.assertEqual(argv[argv.index('--parent') + 1], 't101')
        # the new session can now act: it reports to t101 and may send to its child
        self.host.report('t201', '[리드] 이어 갑니다')
        # backup exists and the restore command names it
        self.assertTrue(all(Path(p).is_file() for p in out['backup']['files'].values()))
        self.assertIn('cp ', out['if_wrong'])

    def test_live_terminal_is_refused_and_nothing_changes(self):
        before = (Path(self.host.mailbox) / 'state.json').read_text()
        hc = FakeHc({'t102': 'live'})
        with self.assertRaisesRegex(ValueError, 'still live'):
            self.host.takeover('t101', 't102', run=hc)
        self.assertEqual(hc.runs(), [])
        self.assertEqual((Path(self.host.mailbox) / 'state.json').read_text(), before)

    def test_unknown_hc_state_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'Cannot verify'):
            self.host.takeover('t101', 't102', run=FakeHc({'t102': 'hc-down'}))

    def test_a_terminal_hc_no_longer_knows_counts_as_ended(self):
        out = self.host.takeover('t101', 't102', run=FakeHc({}))
        self.assertEqual(out['old_terminal'], 'not_found')

    def test_root_director_can_be_taken_over_from_any_terminal(self):
        with self.host.locked() as state:
            state['nodes']['t101']['resumed_session'] = SID
            self.host.commit(state)
        hc = FakeHc({'t101': 'finished'}, next_address='t300')
        out = self.host.takeover('some-unregistered-terminal', 't101', model='claude-fable-5-1', run=hc)
        s = self.state()
        self.assertIsNone(s['nodes']['t300']['parent'])
        self.assertEqual(s['nodes']['t300']['role'], 'secretary')
        self.assertEqual(s['nodes']['t102']['parent'], 't300')
        self.assertEqual(out['moved']['children'], ['t102'])
        self.assertIn('--no-parent', hc.runs()[0])
        self.assertEqual([r['report_id'] for r in self.host.inbox('t300')], ['r-to-director'])
        # then the new director takes over its ended lead, one level at a time
        hc2 = FakeHc({'t102': 'finished'}, next_address='t301')
        self.host.takeover('t300', 't102', run=hc2)
        self.assertEqual(self.state()['nodes']['t103']['parent'], 't301')

    def test_only_the_parent_may_take_over_a_child(self):
        hc = FakeHc({'t103': 'finished'})
        with self.assertRaisesRegex(ValueError, 'Only the registered parent'):
            self.host.takeover('t101', 't103', resume=SID, run=hc)

    def test_codex_cannot_resume_and_fresh_needs_a_task(self):
        with self.host.locked() as state:
            state['nodes']['t103']['vendor'] = 'codex'
            self.host.commit(state)
        hc = FakeHc({'t103': 'finished'})
        with self.assertRaisesRegex(ValueError, 'cannot be reopened'):
            self.host.takeover('t102', 't103', resume=SID, run=hc)
        with self.assertRaisesRegex(ValueError, 'cannot be reopened'):
            self.host.takeover('t102', 't103', run=hc)
        out = self.host.takeover('t102', 't103', fresh=True, task='Read lead-state.md first', run=hc)
        self.assertIn('Codex: started a new conversation', out['notes'][0])
        argv = hc.runs()[0]
        self.assertNotIn('--resume', argv)
        self.assertIn('Read lead-state.md first', argv[-1])

    def test_claude_without_a_known_session_id_needs_resume_or_fresh(self):
        with self.host.locked() as state:
            state['nodes']['t102'].pop('resumed_session')
            state['nodes']['t102'].pop('session_id', None)   # B21: spawn now records one
            self.host.commit(state)
        with self.assertRaisesRegex(ValueError, '--resume'):
            self.host.takeover('t101', 't102', run=FakeHc({'t102': 'finished'}))

    def test_failed_launch_leaves_the_mailbox_and_prints_the_restore_command(self):
        before = (Path(self.host.mailbox) / 'state.json').read_text()
        def broken(args, **kwargs):
            if args[1] == 'get':
                return subprocess.CompletedProcess(args, 0, '{"state": "finished"}', '')
            return subprocess.CompletedProcess(args, 1, '', 'boom')
        with self.assertRaisesRegex(RuntimeError, 'To restore the mailbox .*cp '):
            self.host.takeover('t101', 't102', run=broken)
        self.assertEqual((Path(self.host.mailbox) / 'state.json').read_text(), before)

    def test_dry_run_changes_nothing(self):
        before = (Path(self.host.mailbox) / 'state.json').read_text()
        hc = FakeHc({'t102': 'finished'})
        out = self.host.takeover('t101', 't102', run=hc, dry_run=True)
        self.assertIn('--resume', out['argv'])
        self.assertEqual(hc.runs(), [])
        self.assertEqual((Path(self.host.mailbox) / 'state.json').read_text(), before)


if __name__ == '__main__':
    unittest.main()
