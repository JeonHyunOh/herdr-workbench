"""B2 close follows a git-proven branch rename; B11 discard cleans a spawn that failed before hc ran."""
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
import test_bench
import test_worktree



class RenameClose(unittest.TestCase):
    setUp = test_worktree.WorktreeContract.setUp
    git = test_worktree.WorktreeContract.git
    worker = test_worktree.WorktreeContract.worker
    close = test_worktree.WorktreeContract.close
    spawn = test_worktree.WorktreeContract.spawn

    def renamed_and_committed(self, new='docs/renamed-task', push=True):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        (wt / 'result.txt').write_text('worker result')
        self.git(wt, 'add', 'result.txt')
        self.git(wt, 'commit', '-m', 'worker result')
        self.git(wt, 'branch', '-m', new)          # renamed before push, as in 11/10 t2b
        if push:
            self.git(wt, 'push', '-u', 'origin', new)
        return wt

    def test_renamed_pushed_and_merged_branch_is_cleaned_under_its_new_name(self):
        wt = self.renamed_and_committed()
        self.git(self.repo, 'merge', '--ff-only', 'docs/renamed-task')
        self.git(self.repo, 'push', 'origin', 'main')
        result = self.close()
        self.assertEqual(result['status'], 'closed', result['reason'])
        self.assertTrue(result['worktree_removed'])
        self.assertTrue(result['branch_deleted'])
        self.assertIn('renamed from bench-task', result['reason'])
        self.assertFalse(wt.exists())
        self.assertNotEqual(self.git(self.repo, 'show-ref', '--verify', 'refs/heads/docs/renamed-task', check=False).returncode, 0)
        record = next(n for n in self.host.inspect()['nodes'] if n['address'] == 't3')['worktree']
        self.assertEqual((record['branch'], record['renames'][0]['from']), ('docs/renamed-task', 'bench-task'))

    def test_renamed_pushed_unmerged_branch_removes_worktree_and_keeps_branch(self):
        wt = self.renamed_and_committed()
        result = self.close()
        self.assertEqual(result['status'], 'closed', result['reason'])
        self.assertFalse(result['branch_deleted'])
        self.assertIn('not merged', result['reason'])
        self.assertFalse(wt.exists())
        self.assertEqual(self.git(self.repo, 'rev-parse', '--verify', 'refs/heads/docs/renamed-task').returncode, 0)

    def test_renamed_but_unpushed_branch_is_preserved(self):
        wt = self.renamed_and_committed(push=False)
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('unpushed', result['reason'])
        self.assertTrue(wt.exists())

    def test_two_renames_are_followed(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        self.git(wt, 'branch', '-m', 'second')
        self.git(wt, 'branch', '-m', 'third')
        self.git(wt, 'push', '-u', 'origin', 'third')
        result = self.close()
        self.assertEqual(result['status'], 'closed', result['reason'])
        self.assertTrue(result['branch_deleted'])   # third points at main's commit: merged

    def test_switch_to_new_branch_is_still_preserved_with_both_names(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        self.git(wt, 'switch', '-c', 'someone-else')
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('someone-else', result['reason'])
        self.assertIn('bench-task', result['reason'])
        self.assertTrue(wt.exists())

    def test_rename_is_not_adopted_when_the_old_name_exists_again(self):
        node = self.worker()
        wt = Path(node['worktree']['path'])
        self.git(wt, 'branch', '-m', 'moved')
        self.git(self.repo, 'branch', 'bench-task', 'main')   # someone recreated the recorded name
        result = self.close()
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(wt.exists())


class DiscardFailedSpawn(unittest.TestCase):
    setUp = test_worktree.WorktreeContract.setUp
    git = test_worktree.WorktreeContract.git
    spawn = test_worktree.WorktreeContract.spawn

    def failed_prelaunch(self, branch='failed-preparation'):
        self.host.config['link_repo_skills'] = str(self.root / 'missing-linker.sh')
        boundary = Mock()
        with self.assertRaises(RuntimeError):
            self.host.spawn('worker-code', 't2', run=boundary, worktree=(str(self.repo), branch))
        boundary.assert_not_called()
        receipt = next(self.host.evidence.glob('spawn-worker-code-*.json'))
        return receipt, Path(json.loads(receipt.read_text())['worktree']['path'])

    def test_parent_discards_untouched_prelaunch_failure_and_retry_is_free(self):
        receipt, wt = self.failed_prelaunch()
        result = self.host.discard('t2', str(wt))
        self.assertEqual(result['status'], 'discarded', result['reason'])
        self.assertTrue(result['worktree_removed'])
        self.assertTrue(result['branch_deleted'])
        self.assertFalse(wt.exists())
        self.assertEqual(json.loads(receipt.read_text())['status'], 'discarded')
        self.assertEqual(self.host.discard('t2', str(wt)), result)   # repeat returns the recorded result
        self.host.config['link_repo_skills'] = str(test_bench.HELPER.parent.parent / 'harness/link-repo-skills.sh')
        run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"address":"t3"}', ''))
        node = self.host.spawn('worker-code', 't2', run=run, worktree=(str(self.repo), 'failed-preparation'))
        self.assertEqual(node['address'], 't3')

    def test_discard_refuses_other_parents_registered_sessions_and_launched_spawns(self):
        _, wt = self.failed_prelaunch()
        with self.assertRaises(ValueError):
            self.host.discard('t1', str(wt))
        with self.assertRaises(ValueError):
            self.host.discard('t2', str(self.root / 'not-a-worktree'))
        self.host.config['link_repo_skills'] = str(test_bench.HELPER.parent.parent / 'harness/link-repo-skills.sh')
        run = Mock(return_value=subprocess.CompletedProcess([], 1, '', 'hc refused'))
        with self.assertRaises(RuntimeError):
            self.host.spawn('worker-code', 't2', run=run, worktree=(str(self.repo), 'launched-branch'))
        launched = [json.loads(p.read_text()) for p in self.host.evidence.glob('spawn-worker-code-*.json')]
        launched_wt = next(r['worktree']['path'] for r in launched if r['worktree']['branch'] == 'launched-branch')
        with self.assertRaisesRegex(ValueError, 'before hc ran'):
            self.host.discard('t2', launched_wt)
        self.assertTrue(Path(launched_wt).exists())

    def test_discard_preserves_any_work_in_the_failed_worktree(self):
        _, wt = self.failed_prelaunch()
        (wt / 'note.txt').write_text('typed by hand')
        result = self.host.discard('t2', str(wt))
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(wt.exists())
        self.git(wt, 'add', 'note.txt')
        self.git(wt, 'commit', '-m', 'hand commit')
        result = self.host.discard('t2', str(wt))
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('unpushed', result['reason'])
        self.assertTrue(wt.exists())
        # Pushed but not merged (the real 11/10 case while its PR is open): worktree goes, branch stays.
        self.git(wt, 'push', '-u', 'origin', 'failed-preparation')
        result = self.host.discard('t2', str(wt))
        self.assertEqual(result['status'], 'discarded', result['reason'])
        self.assertFalse(result['branch_deleted'])
        self.assertIn('not merged', result['reason'])
        self.assertFalse(wt.exists())

    def test_skill_link_gets_two_minutes(self):
        real, seen = subprocess.run, []
        def spy(args, **kwargs):
            if args[:1] == ['bash']:
                seen.append(kwargs.get('timeout'))
            return real(args, **kwargs)
        run = Mock(return_value=subprocess.CompletedProcess([], 0, '{"address":"t3"}', ''))
        with patch.object(self.module.subprocess, 'run', side_effect=spy):
            self.host.spawn('worker-code', 't2', run=run, worktree=(str(self.repo), 'linked'))
        self.assertEqual(seen, [120])


if __name__ == '__main__':
    unittest.main()
