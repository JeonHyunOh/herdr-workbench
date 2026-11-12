"""U9 (2026-11-11): the tree shows the model a session uses now, not only the one it was opened with."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_bench


def line(**entry):
    return json.dumps(entry, ensure_ascii=False)


class ModelNow(unittest.TestCase):
    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.home, ignore_errors=True))
        self.patch = patch.object(self.module.Path, 'home', return_value=self.home)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def claude_log(self, cwd, session, lines):
        folder = self.module.claude_project_dir(cwd)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f'{session}.jsonl').write_text('\n'.join(lines) + '\n')

    def test_set_model_counts_at_once_and_later_answers_win(self):
        path = self.home / 'log.jsonl'
        path.write_text('\n'.join([
            line(type='assistant', message={'model': 'claude-fable-5-1'}),
            line(type='user', message={'content': '<local-command-stdout>Set model to `Opus 5.5` and saved as your default for new sessions</local-command-stdout>'}),
        ]) + '\n')
        self.assertEqual(self.module.claude_model_from_log(path), ('claude-opus-5-5', '/model'))
        with path.open('a') as f:
            f.write(line(type='api-request', params={'model': 'claude-sonnet-5-5'}) + '\n')
        self.assertEqual(self.module.claude_model_from_log(path), ('claude-sonnet-5-5', 'request'))
        with path.open('a') as f:
            f.write(line(type='user', message={'content': '<local-command-stdout>Set model to `Default (recommended)`</local-command-stdout>'}) + '\n')
        self.assertEqual(self.module.claude_model_from_log(path)[0], 'claude-sonnet-5-5', 'an unreadable /model line is ignored')

    def test_only_the_tail_is_read(self):
        path = self.home / 'big.jsonl'
        old = line(type='assistant', message={'model': 'claude-haiku-5-5'})
        path.write_text(old + '\n' + ('x' * 300000) + '\n' + line(type='assistant', message={'model': 'claude-opus-5-5'}) + '\n')
        self.assertEqual(self.module.claude_model_from_log(path)[0], 'claude-opus-5-5')

    def test_codex_reads_turn_context_of_its_own_rollout(self):
        node = {'vendor': 'codex', 'cwd': '/w', 'created_at': '2026-11-11T11:50:40+00:00'}
        folder = self.home / '.codex' / 'sessions' / '2026' / '11' / '11'
        folder.mkdir(parents=True)
        (folder / 'rollout-a.jsonl').write_text('\n'.join([
            line(type='session_meta', payload={'cwd': '/w', 'timestamp': '2026-11-11T11:50:49.943Z'}),
            line(type='turn_context', payload={'model': 'gpt-6-astra'}),
            line(type='turn_context', payload={'model': 'gpt-6.1-sol'})]) + '\n')
        (folder / 'rollout-b.jsonl').write_text(line(type='session_meta', payload={'cwd': '/other', 'timestamp': '2026-11-11T11:50:45Z'}) + '\n')
        self.assertEqual(self.module.model_now(node), ('gpt-6.1-sol', 'turn'))
        node['created_at'] = '2026-11-11T09:00:00+00:00'      # no rollout near the spawn time
        self.assertEqual(self.module.model_now(node), (None, None))

    def test_tree_json_carries_model_now_and_refresh_writes_only_on_change(self):
        test_bench.HostContract.spawn(self, 'secretary', 'operator', 't101')
        test_bench.HostContract.spawn(self, 'lead', 't101', 't102')
        with self.host.locked() as state:
            lead = state['nodes']['t102']
            lead.update(session_id='11111111-2222-3333-4444-555555555555', model='claude-fable-5-1')
            self.host.commit(state)
        self.claude_log(lead['cwd'], lead['session_id'], [line(type='assistant', message={'model': 'claude-fable-5-1'})])
        self.assertTrue(self.host.tree_refresh()['changed'])
        self.assertFalse(self.host.tree_refresh()['changed'], 'nothing changed, nothing written')
        self.claude_log(lead['cwd'], lead['session_id'], [line(type='assistant', message={'model': 'claude-fable-5-1'}),
            line(type='user', message={'content': '<local-command-stdout>Set model to `Opus 5.5`</local-command-stdout>'})])
        self.assertTrue(self.host.tree_refresh()['changed'])
        tree = json.loads((self.host.mailbox / 'tree.json').read_text())
        row = next(n for n in tree['nodes'] if n['address'] == 't102')
        self.assertEqual((row['model'], row['model_now'], row['model_now_source']), ('claude-fable-5-1', 'claude-opus-5-5', '/model'))

    def test_sessions_without_an_id_are_looked_up_once(self):
        test_bench.HostContract.spawn(self, 'secretary', 'operator', 't101')
        with self.host.locked() as state:
            node = state['nodes']['t101']
            for k in ('session_id', 'resumed_session'):
                node.pop(k, None)
            node['display'] = 'Director'
            self.host.commit(state)
        sid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        self.claude_log(node['cwd'], sid, [line(type='custom-title', customTitle='Director'),
                                           line(type='assistant', message={'model': 'claude-opus-5-5'})])
        with patch.object(self.module, 'find_claude_session', wraps=self.module.find_claude_session) as finder:
            self.host.tree_refresh()
            self.host.tree_refresh()
        self.assertEqual(finder.call_count, 1, 'the found id is kept, so the folder is scanned once')
        state = json.loads((self.host.mailbox / 'state.json').read_text())
        self.assertEqual(state['nodes']['t101']['session_id'], sid)
        self.assertEqual(state['nodes']['t101']['session_id_source'], 'title')


if __name__ == '__main__':
    unittest.main()
