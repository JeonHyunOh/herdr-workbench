"""Real local Git verifies preservation, ownership, remote freshness and deletion."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock
import test_bench


class WorktreeContract(unittest.TestCase):
    spawn = test_bench.HostContract.spawn
    # Inherit the host fixture, not its tests.
    def setUp(self):
        test_bench.HostContract.setUp(self)
        for role in ['worker-code', 'worker-query']:
            (self.root / 'roles' / (role + '.md')).write_text('Fixture worker role')
        self.repo = self.root / 'fixture'
        self.remote = self.root / 'remote.git'
        # T1 (11/12 t6f): name the remote's branch; a bare init otherwise follows init.defaultBranch.
        self.git(self.root, 'init', '--bare', '-b', 'main', str(self.remote))
        self.git(self.repo, 'init', '-b', 'main')
        self.git(self.repo, 'config', 'user.name', 'Fixture')
        self.git(self.repo, 'config', 'user.email', 'fixture@localhost')
        skill = self.repo / '.claude/skills/example/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('Example fixture skill')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-m', 'fixture seed')
        self.git(self.repo, 'remote', 'add', 'origin', str(self.remote))
        self.git(self.repo, 'push', '-u', 'origin', 'main')
        self.spawn('secretary', 'operator', 't1')
        self.spawn('lead', 't1', 't2')

    def git(self, repo, *args, check=True):
        p = subprocess.run(['git', '-C', str(repo), *args], text=True, capture_output=True)
        if check and p.returncode:
            self.fail(p.stderr)
        return p

    def worker(self):
        run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"address":"t3"}', ''))
        self.assertTrue(hasattr(self.host, 'worktree_plan'), 'Worktree lifecycle is missing')
        return self.host.spawn('worker-code', 't2', run=run, worktree=(str(self.repo), 'bench-task'))

    def close(self, caller='t2'):
        def hc(args, **kwargs):
            if args[1] == 'get':
                return subprocess.CompletedProcess(args, 0, '{"state":"live"}', '')
            return subprocess.CompletedProcess(args, 0, '{}', '')
        return self.host.close(caller, 't3', run=hc)

    def commit_worker(self, node, push=False):
        wt = Path(node['worktree']['path'])
        (wt / 'result.txt').write_text('worker result')
        self.git(wt, 'add', 'result.txt')
        self.git(wt, 'commit', '-m', 'worker result')
        if push:
            self.git(wt, 'push', '-u', 'origin', 'bench-task')
        return wt

    def test_worktree_creation_links_skills_and_records_creator(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        self.assertEqual(self.git(wt, 'branch', '--show-current').stdout.strip(), 'bench-task')
        self.assertTrue((wt / '.agents/skills/example/SKILL.md').is_file())
        self.assertEqual(node['worktree']['created_by'], 't2')
        self.assertTrue(node['worktree']['branch_created'])
        self.assertEqual(node['cwd'], str(wt))

    def test_existing_branch_and_foreign_parent_are_not_adopted(self):
        self.git(self.repo, 'branch', 'bench-task')
        with self.assertRaises(ValueError): self.worker()
        self.assertEqual(len(self.host.inspect()['nodes']), 2)

    def test_close_merged_local_branch_deletes_and_reports_once(self):
        node = self.worker()
        wt = self.commit_worker(node, push=True)
        self.git(self.repo, 'merge', '--ff-only', 'bench-task')
        self.git(self.repo, 'push', 'origin', 'main')
        result = self.close()
        self.assertEqual(result['status'], 'closed')
        self.assertTrue(result['branch_deleted'])
        self.assertFalse(wt.exists())
        self.assertNotEqual(self.git(self.repo, 'show-ref', '--verify', 'refs/heads/bench-task', check=False).returncode, 0)
        self.assertEqual(self.close(), result)
        self.assertEqual(len(self.host.inbox('t2')), 1)

    def test_close_pushed_unmerged_branch_is_preserved_with_reason(self):
        node = self.worker()
        wt = self.commit_worker(node, push=True)
        result = self.close()
        self.assertEqual(result['status'], 'closed')
        self.assertFalse(result['branch_deleted'])
        self.assertIn('not merged', result['reason'])
        self.assertFalse(wt.exists())
        self.assertEqual(self.git(self.repo, 'rev-parse', '--verify', 'refs/heads/bench-task').returncode, 0)
        self.assertEqual(len(self.host.inbox('t2')), 1)

    def test_dirty_worktree_is_preserved_after_session_stop(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        (wt / 'untracked.txt').write_text('retain this')
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('changes', result['reason'])
        self.assertTrue(wt.exists())
        self.assertEqual((wt / 'untracked.txt').read_text(), 'retain this')

    def test_unpushed_commit_is_preserved(self):
        node = self.worker()
        wt = self.commit_worker(node)
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('unpushed', result['reason'])
        self.assertTrue(wt.exists())

    def test_ignored_user_file_is_preserved(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        exclude = Path(self.git(self.repo, 'rev-parse', '--absolute-git-dir').stdout.strip()) / 'info/exclude'
        with exclude.open('a') as f: f.write('\nprivate.txt\n')
        (wt / 'private.txt').write_text('keep')
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(wt.exists())

    def test_wrong_parent_cannot_close_and_children_block_parent_close(self):
        self.worker()
        with self.assertRaises(ValueError): self.close('t1')
        with self.assertRaises(ValueError): self.host.close('t1', 't2')

    def test_remote_unavailable_blocks_cleanup(self):
        node = self.worker()
        self.git(self.repo, 'remote', 'set-url', 'origin', str(self.root / 'missing.git'))
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(Path(node['worktree']['path']).exists())

    def test_switched_branch_is_not_removed(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        self.git(wt, 'switch', '-c', 'someone-else')
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(wt.exists())

    def test_missing_ownership_evidence_preserves_branch(self):
        node = self.worker()
        with self.host.locked() as state:
            state['nodes']['t3']['worktree']['branch_created'] = False
            self.host.commit(state)
        result = self.close()
        self.assertFalse(result['branch_deleted'])
        self.assertIn('ownership', result['reason'])

    def test_policy_removal_prevents_branch_deletion(self):
        self.worker()
        self.host.config['policy'] = str(self.root / 'no-policy.yaml')
        result = self.close()
        self.assertFalse(result['branch_deleted'])
        self.assertIn('policy', result['reason'])

    def test_failed_native_spawn_preserves_worktree_and_receipt(self):
        self.assertTrue(hasattr(self.host, 'worktree_plan'), 'Worktree lifecycle is missing')
        run = Mock(return_value=subprocess.CompletedProcess([], 1, '', 'no CLI'))
        with self.assertRaises(RuntimeError):
            self.host.spawn('worker-code', 't2', run=run, worktree=(str(self.repo), 'bench-task'))
        receipts = [json.loads(p.read_text()) for p in self.host.evidence.glob('spawn-worker-*.json')]
        self.assertEqual(len(receipts), 1)
        self.assertTrue(Path(receipts[0]['worktree']['path']).exists())
        self.assertEqual(len(self.host.inspect()['nodes']), 2)

    def test_retry_after_hc_rejection_explains_and_preserves_unregistered_worktree(self):
        rejected = Mock(return_value=subprocess.CompletedProcess(
            [], 1, '', '{"error":{"kind":"name_taken"}}'))
        with self.assertRaises(RuntimeError):
            self.host.spawn('worker-code', 't2', run=rejected,
                            worktree=(str(self.repo), 'bench-task'))
        record = next(self.host.evidence.glob('spawn-worker-*.json'))
        original_receipt = record.read_bytes()
        wt = Path(json.loads(original_receipt)['worktree']['path'])
        (wt / 'keep.txt').write_text('preserved after failed launch\n')
        before_worktrees = self.git(self.repo, 'worktree', 'list', '--porcelain').stdout
        before_branch = self.git(self.repo, 'rev-parse', 'bench-task').stdout
        retry = Mock()
        with self.assertRaisesRegex(ValueError, 'Failed spawn preserved worktree') as caught:
            self.host.spawn('worker-code', 't2', run=retry,
                            worktree=(str(self.repo), 'bench-task'))
        self.assertIn(str(wt), str(caught.exception))
        self.assertIn(str(record), str(caught.exception))
        self.assertIn('registration is not confirmed', str(caught.exception))
        retry.assert_not_called()
        self.assertEqual(record.read_bytes(), original_receipt)
        self.assertEqual(len(list(self.host.evidence.glob('spawn-worker-*.json'))), 1)
        self.assertEqual((wt / 'keep.txt').read_text(), 'preserved after failed launch\n')
        self.assertEqual(self.git(self.repo, 'worktree', 'list', '--porcelain').stdout, before_worktrees)
        self.assertEqual(self.git(self.repo, 'rev-parse', 'bench-task').stdout, before_branch)
        self.assertEqual(len(self.host.inspect()['nodes']), 2)




# B22 (11/11 21:56): t56's Planning worktree branched from the main checkout's meeting branch, 188 commits
# behind origin/main. A new worktree must start from origin's default branch after a fetch.
class WorktreeBase(unittest.TestCase):
    setUp, git, worker = WorktreeContract.setUp, WorktreeContract.git, WorktreeContract.worker
    spawn = test_bench.HostContract.spawn

    def commit(self, repo, name):
        (repo / name).write_text(name)
        self.git(repo, 'add', name)
        self.git(repo, 'commit', '-m', name)
        return self.git(repo, 'rev-parse', 'HEAD').stdout.strip()

    def test_main_checkout_on_an_old_side_branch_does_not_leak(self):
        self.git(self.repo, 'checkout', '-b', 'meeting/old')
        self.commit(self.repo, 'meeting-notes.md')
        origin_main = self.git(self.repo, 'rev-parse', 'origin/main').stdout.strip()
        node = self.worker()
        wt = Path(node['worktree']['path'])
        self.assertEqual(node['worktree']['base'], origin_main)
        self.assertEqual(node['worktree']['base_ref'], 'refs/remotes/origin/main')
        self.assertEqual(self.git(wt, 'rev-parse', 'HEAD').stdout.strip(), origin_main)
        self.assertFalse((wt / 'meeting-notes.md').exists(), 'nothing from the side branch')
        self.assertEqual(self.git(self.repo, 'branch', '--show-current').stdout.strip(), 'meeting/old', 'main checkout untouched')

    def test_origin_ahead_of_the_local_clone_is_fetched_first(self):
        other = self.root / 'other-clone'
        self.git(self.root, 'clone', str(self.remote), str(other))
        self.git(other, 'config', 'user.name', 'Other')
        self.git(other, 'config', 'user.email', 'other@localhost')
        newer = self.commit(other, 'newer.md')
        self.git(other, 'push', 'origin', 'HEAD:main')
        self.assertNotEqual(self.git(self.repo, 'rev-parse', 'origin/main').stdout.strip(), newer, 'local copy is stale')
        node = self.worker()
        self.assertEqual(node['worktree']['base'], newer)

    def test_origin_head_names_the_default_branch(self):
        self.git(self.repo, 'push', 'origin', 'main:trunk')
        self.git(self.repo, 'checkout', '-b', 'local-only')
        self.commit(self.repo, 'local.md')
        self.git(self.repo, 'push', 'origin', 'local-only:trunk', '--force')
        trunk = self.git(self.repo, 'rev-parse', 'HEAD').stdout.strip()
        self.git(self.repo, 'checkout', 'main')
        self.git(self.repo, 'fetch', 'origin')
        self.git(self.repo, 'symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/trunk')
        node = self.worker()
        self.assertEqual((node['worktree']['base_ref'], node['worktree']['base']), ('refs/remotes/origin/trunk', trunk))

    def test_no_reachable_origin_refuses_without_creating_anything(self):
        self.git(self.repo, 'remote', 'set-url', 'origin', str(self.root / 'missing.git'))
        before = self.git(self.repo, 'worktree', 'list', '--porcelain').stdout
        with self.assertRaisesRegex(RuntimeError, 'fetch origin failed'):
            self.worker()
        self.assertEqual(self.git(self.repo, 'worktree', 'list', '--porcelain').stdout, before)
        self.assertNotEqual(self.git(self.repo, 'show-ref', '--verify', 'refs/heads/bench-task', check=False).returncode, 0)

# B19 (11/11 t3f): a worktree's node_modules can be a symlink to the main checkout's node_modules.
# Git lists such a link as one ignored entry. Close must accept it, unlink only the link and never
# follow it: the main checkout's packages must survive (the 'rm -rf node_modules/' trap).
class SymlinkedOutputs(unittest.TestCase):
    # Borrow the fixture only, so WorktreeContract's tests do not run twice.
    setUp, git, worker, close = (WorktreeContract.setUp, WorktreeContract.git,
                                 WorktreeContract.worker, WorktreeContract.close)
    spawn = test_bench.HostContract.spawn

    def link_into_worktree(self, names):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        exclude = Path(self.git(self.repo, 'rev-parse', '--absolute-git-dir').stdout.strip()) / 'info/exclude'
        with exclude.open('a') as stream: stream.write('\nnode_modules\nprivate-link\n')
        targets = []
        for name in names:
            target = self.repo / name                     # the main checkout's real directory
            (target / 'package').mkdir(parents=True, exist_ok=True)
            (target / 'package' / 'index.js').write_text('main checkout package')
            link = wt / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target, target_is_directory=True)
            targets.append(target)
        return wt, targets

    def test_symlinked_node_modules_closes_and_targets_survive(self):
        wt, targets = self.link_into_worktree(['node_modules', 'infra/node_modules'])
        self.assertIn('node_modules', self.git(wt, 'ls-files', '--others', '--ignored', '--exclude-standard').stdout.split())
        result = self.close()
        self.assertEqual(result['status'], 'closed', result['reason'])
        self.assertFalse(wt.exists())
        for target in targets:
            self.assertEqual((target / 'package' / 'index.js').read_text(), 'main checkout package')

    def test_a_plain_file_named_node_modules_is_still_preserved(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        exclude = Path(self.git(self.repo, 'rev-parse', '--absolute-git-dir').stdout.strip()) / 'info/exclude'
        with exclude.open('a') as stream: stream.write('\nnode_modules\n')
        (wt / 'node_modules').write_text('not a link, not generated')
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual((wt / 'node_modules').read_text(), 'not a link, not generated')

    def test_a_symlink_with_another_name_is_still_preserved(self):
        wt, _ = self.link_into_worktree([])
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'keep.txt').write_text('keep')
        (wt / 'private-link').symlink_to(outside, target_is_directory=True)
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue((wt / 'private-link').is_symlink())
        self.assertEqual((outside / 'keep.txt').read_text(), 'keep')

    def test_the_rule_needs_the_real_link_not_just_the_name(self):
        import bench
        self.assertFalse(bench.regenerable_output('node_modules'))            # no root: name alone is not enough
        self.assertFalse(bench.regenerable_output('node_modules', root=self.root))  # nothing there

# Each policy-listed output must allow cleanup; an unrelated ignored file remains covered above.
def generated_output_case(relative):
    def test(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        file = wt / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('regenerable fixture output')
        exclude = Path(self.git(self.repo, 'rev-parse', '--absolute-git-dir').stdout.strip()) / 'info/exclude'
        with exclude.open('a') as stream: stream.write('\n' + relative + '\n')
        result = self.close()
        self.assertEqual(result['status'], 'closed', result['reason'])
        self.assertFalse(wt.exists())
    return test

for label, relative in [
    ('node_modules', 'app/node_modules/package/index.js'), ('dotvenv', '.venv/bin/python'),
    ('venv', 'venv/bin/python'), ('pycache', 'pkg/__pycache__/main.pyc'),
    ('pytest', '.pytest_cache/v/cache/items'), ('mypy', '.mypy_cache/index.json'),
    ('ruff', '.ruff_cache/entry'), ('dist', 'dist/app.js'), ('build', 'app/build/output'),
    ('cdk', 'cdk.out/template.json'), ('coverage_dir', 'coverage/index.html'),
    ('coverage_file', '.coverage'), ('tsbuildinfo', 'app/tsconfig.tsbuildinfo'),
    ('agents', '.agents/generated.json'), ('codex', '.codex/hooks.json'),
    ('claude_local', '.claude/settings.local.json'), ('dsstore', '.DS_Store')]:
    setattr(WorktreeContract, 'test_generated_' + label + '_allows_close', generated_output_case(relative))


def test_lead_can_work_alone_and_secretary_closes_owned_worktree(self):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"address":"t4"}', ''))
    node = self.host.spawn('lead', 't1', vendor='codex', run=run,
                           worktree=(str(self.repo), 'lead-alone'))
    argv = run.call_args.args[0]
    self.assertEqual(argv[argv.index('--sandbox') + 1], 'workspace-write')
    wt = Path(node['worktree']['path'])
    self.assertTrue((wt / '.agents/skills/example/SKILL.md').is_file())
    def hc(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, '{"state":"finished"}', '')
    result = self.host.close('t1', 't4', run=hc)
    self.assertEqual(result['status'], 'closed', result['reason'])
    self.assertTrue(result['branch_deleted'])
    self.assertFalse(wt.exists())
    self.assertEqual(len(self.host.inbox('t1')), 1)

WorktreeContract.test_lead_can_work_alone_and_secretary_closes_owned_worktree = test_lead_can_work_alone_and_secretary_closes_owned_worktree


def hidden_index_case(flag):
    def test(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        relative = '.claude/skills/example/SKILL.md'
        self.git(wt, 'update-index', flag, relative)
        (wt / relative).write_text('uncommitted hidden user edit')
        self.assertEqual(self.git(wt, 'status', '--porcelain').stdout, '')
        result = self.close()
        self.assertEqual(result['status'], 'blocked', result['reason'])
        self.assertTrue(wt.exists())
        self.assertEqual((wt / relative).read_text(), 'uncommitted hidden user edit')
    return test

WorktreeContract.test_assume_unchanged_preserves_hidden_edit = hidden_index_case('--assume-unchanged')
WorktreeContract.test_skip_worktree_preserves_hidden_edit = hidden_index_case('--skip-worktree')


def test_deleted_remote_branch_does_not_count_as_pushed(self):
    node = self.worker()
    wt = self.commit_worker(node, push=True)
    # Test-only bare ref mutation models a remote branch that no longer exists.
    self.git(self.remote, 'update-ref', '-d', 'refs/heads/bench-task')
    result = self.close()
    self.assertEqual(result['status'], 'blocked', result['reason'])
    self.assertIn('unpushed', result['reason'])
    self.assertTrue(wt.exists())

WorktreeContract.test_deleted_remote_branch_does_not_count_as_pushed = test_deleted_remote_branch_does_not_count_as_pushed


def test_prelaunch_link_failure_does_not_block_unrelated_spawn(self):
    self.host.config['link_repo_skills'] = str(self.root / 'missing-linker.sh')
    boundary = Mock(return_value=subprocess.CompletedProcess([], 0, '{"address":"t3"}', ''))
    with self.assertRaisesRegex(RuntimeError, 'Skill link failed'):
        self.host.spawn('worker-code', 't2', run=boundary, worktree=(str(self.repo), 'failed-preparation'))
    self.assertEqual(boundary.call_count, 0)
    receipt = next(self.host.evidence.glob('spawn-worker-code-*.json'))
    failed = json.loads(receipt.read_text())
    self.assertTrue(Path(failed['worktree']['path']).exists())
    another = Mock(return_value=subprocess.CompletedProcess([], 0, '{"address":"t4"}', ''))
    node = self.host.spawn('lead', 't1', run=another)
    self.assertEqual(node['address'], 't4')
    self.assertEqual(len(self.host.inspect()['nodes']), 3)

WorktreeContract.test_prelaunch_link_failure_does_not_block_unrelated_spawn = test_prelaunch_link_failure_does_not_block_unrelated_spawn
