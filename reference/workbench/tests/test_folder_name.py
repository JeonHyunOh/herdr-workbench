"""B25 (2026-11-12 운영자): the tree shows, next to each session's name, the folder name it was opened in.

Names only, never paths (운영자 15:19). A worktree shows the repository it belongs to; a repository opened at
its root shows that repository; the hub shows hub; anything else shows the folder's last name.
"""
import json
import tempfile
import unittest
from pathlib import Path
import test_bench
from test_ls_rename_wait import hc_ls

HUB = Path('/Users/someone/Project/work/hub')
ROOT = HUB / '_my/tools/workbench/worktrees'


class FolderRule(unittest.TestCase):
    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.name = self.module.folder_name

    def test_repository_opened_at_its_root_shows_the_repository(self):
        self.assertEqual(self.name(str(HUB / 'team-repo'), {}, ROOT), 'team-repo')
        self.assertEqual(self.name(str(HUB / 'planning-repo'), {}, ROOT), 'planning-repo')
        self.assertEqual(self.name(str(HUB / 'ops-repo'), {}, ROOT), 'ops-repo')

    def test_hub_shows_its_folder_name(self):
        self.assertEqual(self.name(str(HUB), {}, ROOT), 'hub')

    def test_bench_worktree_shows_the_repository_its_record_names(self):
        repos = {str(ROOT / 'worker-444ec1455025'): str(HUB / 'planning-repo')}
        self.assertEqual(self.name(str(ROOT / 'worker-444ec1455025'), repos, ROOT), 'planning-repo')
        self.assertEqual(self.name(str(ROOT / 'worker-444ec1455025' / 'web' / 'src'), repos, ROOT), 'planning-repo')

    def test_reviewer_opened_in_another_sessions_worktree_shows_that_repository(self):
        nodes = [{'address': 't5n', 'cwd': str(ROOT / 'worker-3aedd212b6d7'),
                  'worktree': {'path': str(ROOT / 'worker-3aedd212b6d7'), 'repo': str(HUB / 'team-repo')}},
                 {'address': 't5r', 'cwd': str(ROOT / 'worker-3aedd212b6d7')}]   # review worker: no worktree of its own
        repos = self.module.worktree_repos(nodes)
        self.assertEqual(self.name(nodes[1]['cwd'], repos, ROOT), 'team-repo')

    def test_bench_worktree_without_a_record_reads_its_git_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / 'worktrees'
            (root / 'worker-aaaa').mkdir(parents=True)
            (root / 'worker-aaaa' / '.git').write_text(f'gitdir: {HUB}/ops-repo/.git/worktrees/worker-aaaa\n')
            (root / 'worker-bbbb').mkdir()
            self.assertEqual(self.name(str(root / 'worker-aaaa'), {}, root), 'ops-repo')
            # Neither a record nor a readable .git file: the folder's own name, never a guess.
            self.assertEqual(self.name(str(root / 'worker-bbbb'), {}, root), 'worker-bbbb')

    def test_claude_worktree_shows_the_repository(self):
        self.assertEqual(self.name(str(HUB / 'team-repo/.claude/worktrees/spot-w2-control'), {}, ROOT), 'team-repo')
        self.assertEqual(self.name(str(HUB / 'team-repo/.claude/worktrees/spot-w2-control/infra'), {}, ROOT), 'team-repo')
        # The worktrees folder itself is not a worktree.
        self.assertEqual(self.name(str(HUB / 'team-repo/.claude/worktrees'), {}, ROOT), 'worktrees')

    def test_any_other_folder_shows_its_last_name(self):
        self.assertEqual(self.name(str(HUB / '_my/docs/intent-requirements/drafts'), {}, ROOT), 'drafts')
        self.assertEqual(self.name(str(HUB / 'team-repo/web'), {}, ROOT), 'web')
        self.assertEqual(self.name('/Users/someone/Project/work/self', {}, ROOT), 'self')

    def test_no_cwd_on_record_shows_nothing(self):
        self.assertIsNone(self.name(None, {}, ROOT))
        self.assertIsNone(self.name('', {}, ROOT))


class FolderInTreeAndLs(unittest.TestCase):
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.spawn('secretary', 'operator', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')
        root = self.host.worktrees_root()
        with self.host.locked() as state:
            state['nodes']['t102']['cwd'] = str(root / 'worker-1234')
            state['nodes']['t102']['worktree'] = {'path': str(root / 'worker-1234'), 'repo': str(self.root / 'team-repo'),
                                                  'branch': 'feat/x'}
            state['nodes']['t103']['cwd'] = str(root / 'worker-1234')
            state['nodes']['t101'].pop('cwd')
            self.host.commit(state)

    def test_tree_json_carries_the_folder_name(self):
        tree = json.loads((self.host.mailbox / 'tree.json').read_text())
        folders = {n['address']: n['folder'] for n in tree['nodes']}
        self.assertEqual(folders, {'t101': None, 't102': 'team-repo', 't103': 'team-repo'})

    def test_spawned_session_shows_the_folder_it_was_opened_in(self):
        self.spawn('lead', 't101', 't104')
        tree = json.loads((self.host.mailbox / 'tree.json').read_text())
        self.assertEqual(next(n for n in tree['nodes'] if n['address'] == 't104')['folder'], 'fixture')

    def test_ls_rows_and_text_carry_the_folder_name(self):
        rows = self.host.ls(run=hc_ls([]))
        self.assertEqual({r['address']: r['folder'] for r in rows}, {'t101': None, 't102': 'team-repo', 't103': 'team-repo'})
        lines = self.module.format_ls(rows).splitlines()
        self.assertTrue(lines[1].strip().startswith('t102  ') and '  team-repo  [lead' in lines[1], lines[1])
        self.assertIn('  feat/x', lines[1])
        self.assertNotIn('None', lines[0])


if __name__ == '__main__':
    unittest.main()
