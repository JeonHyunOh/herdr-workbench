"""U6 (2026-11-11): bench writes a small tree.json because Herdr reads at most 1 MiB and view.json outgrew it."""
import json
import unittest
import test_bench


class TreeJson(unittest.TestCase):
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.spawn('secretary', 'operator', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')

    def test_tree_json_stays_small_and_carries_what_the_tree_shows(self):
        for i in range(60):   # about 1.8 MB of reports: view.json passes 1 MiB, tree.json must not
            self.host.report('t102', '[리드] ' + '가' * 10000, report_id=f'r-{i}')
        view = (self.host.mailbox / 'view.json').read_bytes()
        tree = json.loads((self.host.mailbox / 'tree.json').read_text())
        self.assertGreater(len(view), 1024 * 1024)
        self.assertLess(len((self.host.mailbox / 'tree.json').read_bytes()), 16 * 1024)
        self.assertEqual(tree['space'], json.loads(view)['space'])
        lead = next(n for n in tree['nodes'] if n['address'] == 't102')
        self.assertEqual(set(lead), set(self.host.TREE_FIELDS))
        self.assertEqual(lead['role'], 'lead')
        self.assertEqual(lead['parent'], 't101')
        self.assertTrue(lead['model'])
        self.assertEqual(next(n for n in tree['nodes'] if n['address'] == 't101')['unread_count'], 60)

    def test_closed_sessions_leave_tree_json(self):
        with self.host.locked() as state:
            state['nodes']['t103']['closed_at'] = '2026-11-11T12:00:00+00:00'
            self.host.commit(state)
        tree = json.loads((self.host.mailbox / 'tree.json').read_text())
        self.assertEqual(sorted(n['address'] for n in tree['nodes']), ['t101', 't102'])


if __name__ == '__main__':
    unittest.main()
