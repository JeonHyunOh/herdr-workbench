"""U4 Herdr tab titles follow the workbench display name (2026-11-10)."""
import json
import subprocess
import unittest
import test_bench


class FakeApp:
    """hc run returns addresses; herdr-app ls returns tabs; tab.rename calls are recorded."""
    def __init__(self, tabs, address='t102'):
        self.tabs, self.address, self.calls = tabs, address, []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        if args[:2] == ['herdr-app', 'ls']:
            return subprocess.CompletedProcess(args, 0, json.dumps({'spaces': [{'tabs': self.tabs}]}), '')
        if args[:3] == ['herdr-app', 'do', 'tab.rename']:
            change = json.loads(args[3])
            for tab in self.tabs:
                if tab['id'] == change['id']:
                    tab['name'] = change['name']
            return subprocess.CompletedProcess(args, 0, '{"ok": true}', '')
        return subprocess.CompletedProcess(args, 0, json.dumps({'address': self.address}), '')

    def renames(self):
        return [json.loads(c[3]) for c in self.calls if c[:3] == ['herdr-app', 'do', 'tab.rename']]


class TabTitles(unittest.TestCase):
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.host.config['herdr_app'] = 'herdr-app'
        self.host.config['tab_title_polls'] = 2
        self.spawn('secretary', 'operator', 't101')

    def test_spawn_names_the_new_tab_after_its_display(self):
        app = FakeApp([{'id': 'tb1', 'name': '내탭', 'terminals': [{'terminal': 't101'}]},
                       {'id': 'tb2', 'name': '2', 'terminals': [{'terminal': 't102'}]}])
        node = self.host.spawn('lead', 't101', run=app, display='정리 리드', task='x')
        self.assertEqual(app.renames(), [{'id': 'tb2', 'name': '정리 리드'}])
        self.assertEqual(node['tab_title']['status'], 'renamed')

    def test_spawn_never_fails_because_the_app_is_absent_or_slow(self):
        def run(args, **kwargs):
            if args[0] == 'herdr-app':
                raise FileNotFoundError('herdr-app')
            return subprocess.CompletedProcess(args, 0, '{"address": "t102"}', '')
        node = self.host.spawn('lead', 't101', run=run, display='리드', task='x')
        self.assertEqual(node['address'], 't102')
        self.assertEqual(node['tab_title']['status'], 'app_unavailable')
        app = FakeApp([], address='t103')   # the app answers but the tab has not appeared yet
        self.host.config['tab_title_polls'] = 2
        node = self.host.spawn('lead', 't101', run=app, display='늦은 리드', task='x')
        self.assertEqual(node['tab_title']['status'], 'no_tab')
        self.assertEqual(app.renames(), [])

    def test_retitle_renames_only_auto_numbered_tabs_and_reports_named_ones(self):
        app = FakeApp([{'id': 'tb2', 'name': '2', 'terminals': [{'terminal': 't102'}]}])
        self.host.spawn('lead', 't101', run=FakeApp([]), display='정리 리드', task='x')
        tabs = [{'id': 'tb1', 'name': '내탭', 'terminals': [{'terminal': 't101'}]},
                {'id': 'tb2', 'name': '16', 'terminals': [{'terminal': 't102'}]},
                {'id': 'tb3', 'name': '3', 'terminals': [{'terminal': 't999'}]}]   # not a workbench session
        with self.host.locked() as state:
            state['nodes']['t101']['display'] = 'Director'
            self.host.commit(state)
        app = FakeApp(tabs)
        results = {r['address']: r for r in self.host.retitle('t101', run=app)}
        self.assertEqual(app.renames(), [{'id': 'tb2', 'name': '정리 리드'}])
        self.assertEqual(results['t101']['status'], 'named_by_person')
        self.assertIn('tab.rename', results['t101']['command'])
        self.assertIn('"name": "Director"', results['t101']['command'])
        self.assertEqual(results['t102']['status'], 'renamed')
        self.assertNotIn('t999', results)
        again = {r['address']: r['status'] for r in self.host.retitle('t101', run=app)}
        self.assertEqual(again['t102'], 'already')

    def test_rename_also_retitles_a_tab_that_still_shows_the_old_display(self):
        app = FakeApp([{'id': 'tb2', 'name': '2', 'terminals': [{'terminal': 't102'}]}])
        self.host.spawn('lead', 't101', run=app, display='정리 리드', task='x')   # tab becomes '정리 리드'
        self.host.rename('t101', 't102', '정리·재분류 리드', run=app)
        self.assertEqual(app.renames()[-1], {'id': 'tb2', 'name': '정리·재분류 리드'})

    def test_workers_without_display_use_their_name(self):
        app = FakeApp([{'id': 'tb2', 'name': '2', 'terminals': [{'terminal': 't102'}]}])
        node = self.host.spawn('lead', 't101', run=app, name='project-lead', task='x')
        self.assertEqual(app.renames(), [{'id': 'tb2', 'name': 'project-lead'}])
        self.assertEqual(node['tab_title']['title'], 'project-lead')



class NoHerdrApp(unittest.TestCase):
    """M7 (11/12 t6f): where there is no Herdr app (inside WSL), herdr_app is left out or empty.
    Tab naming is then off: spawn and retitle never call the app and say 'disabled'."""
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.spawn('secretary', 'operator', 't101')

    def check_off(self):
        app = FakeApp([{'id': 'tb2', 'name': '2', 'terminals': [{'terminal': 't102'}]}])
        node = self.host.spawn('lead', 't101', run=app, display='리드', task='x')
        self.assertEqual(node['address'], 't102')
        self.assertEqual(node['tab_title']['status'], 'disabled')
        self.assertEqual([c for c in app.calls if 'herdr-app' in c[0] or c[0] == ''], [])
        self.assertEqual({r['status'] for r in self.host.retitle('t101', run=app)}, {'disabled'})
        self.assertEqual([c for c in app.calls if 'herdr-app' in c[0] or c[0] == ''], [])

    def test_left_out(self):
        self.assertNotIn('herdr_app', self.host.config)
        self.check_off()

    def test_empty_in_bench_yaml(self):
        raw = json.loads(self.config.read_text())
        raw['herdr_app'] = ''
        self.config.write_text(json.dumps(raw))
        self.assertEqual(self.module.load_config(self.config).get('herdr_app'), '')
        self.host.config['herdr_app'] = ''
        self.check_off()

if __name__ == '__main__':
    unittest.main()
