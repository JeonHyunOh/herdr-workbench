"""B10 live tree view, B3 display rename, B5 longer wait and sender filter (2026-11-10)."""
import json
import subprocess
import sys
import unittest
from unittest.mock import Mock
import test_bench

HELPER = test_bench.HELPER


def hc_ls(terminals):
    return Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({'terminals': terminals}), ''))


class LsContract(unittest.TestCase):
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.spawn('secretary', 'operator', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')
        self.spawn('lead', 't101', 't104')

    def test_ls_joins_live_state_and_tolerates_missing_status(self):
        run = hc_ls([{'address': 't101', 'state': 'live', 'status': 'working', 'where': 'hub / 내탭'},
                     {'address': 't102', 'state': 'live'},            # just launched: no status key
                     {'address': 't103', 'state': 'live', 'status': {'app': 'codex', 'state': 'done'}}])
        rows = self.host.ls(run=run)
        self.assertEqual(run.call_args.args[0], [self.host.config['hc'], 'ls', '--json'])
        by = {r['address']: r for r in rows}
        self.assertEqual(by['t101']['status'], 'working')
        self.assertIsNone(by['t102']['status'])
        self.assertEqual(by['t103']['status'], 'done')
        self.assertEqual(by['t104']['state'], 'not listed')   # registered but not in hc ls
        self.assertEqual(by['t101']['where'], 'hub / 내탭')

    def test_ls_orders_parents_before_children_and_hides_closed_by_default(self):
        with self.host.locked() as state:
            state['nodes']['t104']['closed_at'] = '2026-11-10T00:00:00+00:00'
            self.host.commit(state)
        rows = self.host.ls(run=hc_ls([]))
        self.assertEqual([(r['address'], r['depth']) for r in rows], [('t101', 0), ('t102', 1), ('t103', 2)])
        self.assertIn('t104', [r['address'] for r in self.host.ls(run=hc_ls([]), include_closed=True)])

    def test_ls_reports_unread_counts_and_hc_failure_does_not_hide_records(self):
        self.host.report('t103', 'done', complete=True)
        rows = self.host.ls(run=Mock(return_value=subprocess.CompletedProcess([], 1, '', 'core down')))
        by = {r['address']: r for r in rows}
        self.assertEqual(by['t102']['unread_count'], 1)
        self.assertEqual(by['t102']['state'], 'unknown')

    def test_ls_text_is_one_line_per_node(self):
        text = self.module.format_ls(self.host.ls(run=hc_ls([])))
        self.assertEqual(len(text.strip().splitlines()), 4)
        self.assertTrue(text.splitlines()[1].startswith('  '))


class RenameContract(unittest.TestCase):
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.spawn('secretary', 'operator', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')
        self.spawn('lead', 't101', 't104')

    def labelled(self, returncode=0):
        return Mock(return_value=subprocess.CompletedProcess([], returncode, '{}', 'boom' if returncode else ''))

    def test_self_and_direct_child_rename_update_record_and_label(self):
        apps = json.dumps({'spaces': [{'tabs': [{'id': 'tb1', 'name': '내탭', 'terminals': [{'terminal': 't101'}]}]}]})
        def run(args, **kwargs):
            run.calls.append(args)
            return subprocess.CompletedProcess(args, 0, apps if args[0] == 'herdr-app' else '{}', '')
        run.calls = []
        self.host.config['herdr_app'] = 'herdr-app'
        result = self.host.rename('t101', 't101', 'Director', run=run)
        self.assertEqual(run.calls[0], [self.host.config['hc'], 'label', 't101', 'bench.display=Director'])
        self.assertIn('"id": "tb1"', result['manual_steps'][1])
        self.assertNotIn(['herdr-app', 'do'], [c[:2] for c in run.calls])   # the tab is never renamed for the person
        self.assertEqual(result['display'], 'Director')
        self.assertIn('/rename', ' '.join(result['manual_steps']))
        self.host.rename('t101', 't102', '정리 리드', run=run)
        nodes = {n['address']: n for n in self.host.inspect()['nodes']}
        self.assertEqual((nodes['t101']['display'], nodes['t102']['display']), ('Director', '정리 리드'))
        self.assertEqual(nodes['t101']['display_history'][-1]['to'], 'Director')

    def test_grandchild_sibling_and_bad_names_are_refused_without_labeling(self):
        run = self.labelled()
        for caller, target, name in [('t101', 't103', 'x'), ('t102', 't104', 'x'), ('t102', 't101', 'x'),
                                     ('t101', 't101', ''), ('t101', 't101', 'x' * 33), ('t101', 't101', 'a\nb')]:
            with self.assertRaises(ValueError, msg=(caller, target, name)):
                self.host.rename(caller, target, name, run=run)
        run.assert_not_called()

    def test_label_failure_leaves_record_unchanged(self):
        before = {n['address']: n.get('display') for n in self.host.inspect()['nodes']}
        with self.assertRaises(RuntimeError):
            self.host.rename('t101', 't102', '새 이름', run=self.labelled(1))
        after = {n['address']: n.get('display') for n in self.host.inspect()['nodes']}
        self.assertEqual(before, after)


class WaitContract(unittest.TestCase):
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.spawn('secretary', 'operator', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')
        self.spawn('worker-review', 't102', 't105')

    def test_wait_accepts_up_to_an_hour_for_background_use(self):
        with self.assertRaises(ValueError):
            self.host.wait('t102', timeout=3601)
        self.host.report('t103', 'ready')
        self.assertEqual(self.host.wait('t102', timeout=3600)['status'], 'ready')

    def test_wait_from_ignores_other_senders(self):
        self.host.report('t105', 'other worker')
        result = self.host.wait('t102', timeout=0, sender='t103')
        self.assertEqual(result['status'], 'timeout')
        self.assertEqual(result['reports'], [])
        self.assertEqual(result['pending_report_count'], 1)   # all pending for the caller stay visible as a count
        self.host.report('t103', 'mine')
        result = self.host.wait('t102', timeout=0, sender='t103')
        self.assertEqual((result['status'], [r['from'] for r in result['reports']]), ('ready', ['t103']))

    def test_cli_exposes_ls_rename_and_wait_from(self):
        for tail, flags in [(['ls', '--help'], ('--json', '--all')), (['rename', '--help'], ('--display',)),
                            (['wait', '--help'], ('--from',))]:
            result = subprocess.run([sys.executable, str(HELPER)] + tail, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for flag in flags:
                self.assertIn(flag, result.stdout)


if __name__ == '__main__':
    unittest.main()
