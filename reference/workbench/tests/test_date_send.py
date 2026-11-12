"""B7 week calendar and weekday check, B1 parent-to-child follow-up instructions (2026-11-10)."""
from datetime import date
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
import test_bench

HELPER = test_bench.HELPER
TODAY = date(2026, 11, 10)   # Tuesday


class DateCheck(unittest.TestCase):
    def setUp(self):
        test_bench.HostContract.setUp(self)

    def test_week_calendar_names_today_and_every_day_of_the_iso_week(self):
        text = self.module.week_calendar(TODAY)
        self.assertIn('2026-11-10(화)', text)
        for day in ('11/9(월)', '11/11(수)', '11/12(목)', '11/13(금)', '11/14(토)', '11/15(일)'):
            self.assertIn(day, text)
        self.assertIn('11/16', text)

    def test_mismatches_cover_the_forms_used_in_real_briefs(self):
        wrong = ['2026-11-14(금)', '11/13(목)', '11/14(금요일)', '11월 14일 금요일', '11월 13일(목)',
                 '11/9 화,', '2026.11.13(목)', '11/14 금요일']
        for text in wrong:
            found = self.module.date_mismatches('회의는 ' + text + ' 이다', TODAY)
            self.assertEqual(len(found), 1, text)
        first = self.module.date_mismatches('2026-11-14(금)', TODAY)[0]
        self.assertEqual((first['date'], first['written'], first['actual']), ('2026-11-14', '금', '토'))

    def test_correct_dates_and_ordinary_words_are_not_flagged(self):
        right = ('11/9 월, 11/10 화, 11/11 수(team-repo v0.3.0 staging 릴리즈), 11/12 목, 11/13 금(09:30 회의). '
                 '2026-11-13(금), 11월 13일 금요일, 11/14(토). 11/12 목표 정리, 11/12 수정, 11/12 일정, '
                 '11/15 일 마감, 버전 0.3(월간), 2026/11/14(토), 1-3(월)')
        self.assertEqual(self.module.date_mismatches(right, TODAY), [])

    def test_year_is_inferred_nearest_to_today(self):
        found = self.module.date_mismatches('1/4(월)', TODAY)   # 2027-01-04 is Monday
        self.assertEqual(found, [])
        found = self.module.date_mismatches('1/4(일)', TODAY)
        self.assertEqual(found[0]['date'], '2027-01-04')

    def test_spawn_prompt_carries_this_week_calendar(self):
        with patch.object(self.module, 'today_kst', return_value=TODAY):
            self.spawn('secretary', 'operator', 't101')
            _, argv = self.spawn_lead('11/13(금) 09:30 전에 보고')
        prompt = argv[-1]
        self.assertIn('[작업대 달력]', prompt)
        self.assertIn('2026-11-10(화)', prompt)
        self.assertLess(prompt.index('[작업대 달력]'), prompt.index('11/13(금) 09:30 전에 보고'))

    def test_spawn_refuses_wrong_weekday_before_any_launch_or_record(self):
        with patch.object(self.module, 'today_kst', return_value=TODAY):
            self.spawn('secretary', 'operator', 't101')
            boundary = Mock()
            with self.assertRaises(ValueError) as caught:
                self.host.spawn('lead', 't101', run=boundary, task='최종 보고 2026-11-14(금)')
            self.assertIn('11-14(금)', str(caught.exception))
            self.assertIn('토', str(caught.exception))
            self.assertIn('--allow-date-mismatch', str(caught.exception))
            boundary.assert_not_called()
            self.assertEqual(len(list(self.host.evidence.glob('spawn-lead-*.json'))), 0)
            node, _ = self.spawn_lead('최종 보고 2026-11-14(금)', allow_date_mismatch=True)
            self.assertEqual(node['role'], 'lead')

    def spawn_lead(self, task, **kwargs):
        boundary = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({'address': 't102'}), ''))
        node = self.host.spawn('lead', 't101', run=boundary, task=task, **kwargs)
        return node, boundary.call_args.args[0]

    spawn = test_bench.HostContract.spawn


class SendContract(unittest.TestCase):
    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.spawn('secretary', 'operator', 't101')
        self.spawn('lead', 't101', 't102')
        self.spawn('worker-review', 't102', 't103')

    spawn = test_bench.HostContract.spawn

    def sent(self, stdout='{"turn":3,"status":"done","started":true}', returncode=0):
        return Mock(return_value=subprocess.CompletedProcess([], returncode, stdout, ''))

    def test_send_reaches_registered_direct_child_without_force_and_records_text(self):
        run = self.sent()
        with patch.object(self.module, 'today_kst', return_value=TODAY):
            record = self.host.send('t102', 't103', '- 1번을 다시 확인하고 11/13(금) 전에 보고', run=run)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:2], [self.host.config['hc'], 'send'])
        self.assertNotIn('--force', argv)
        self.assertEqual(argv[-3:], ['--', 't103', '- 1번을 다시 확인하고 11/13(금) 전에 보고'])
        self.assertEqual(record['status'], 'sent')
        self.assertEqual((record['from'], record['to']), ('t102', 't103'))
        view = self.host.inspect()
        self.assertEqual(view['directives'][0]['directive_id'], record['directive_id'])
        self.assertEqual(view['directives'][0]['text'], '- 1번을 다시 확인하고 11/13(금) 전에 보고')
        # A follow-up instruction is not a report: no dot, no inbox entry for either side.
        self.assertEqual(self.host.inbox('t103'), [])
        self.assertEqual(self.host.inbox('t102'), [])

    def test_send_passes_status_condition_through(self):
        run = self.sent()
        self.host.send('t102', 't103', '다음 단계 진행', run=run, if_status='idle')
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index('--if') + 1], 'idle')
        self.assertLess(argv.index('--if'), argv.index('--'))
        with self.assertRaises(ValueError):
            self.host.send('t102', 't103', '다음 단계', run=run, if_status='blocked')

    def test_send_refuses_grandchild_parent_unknown_closed_and_empty(self):
        run = self.sent()
        for caller, target in [('t101', 't103'), ('t103', 't102'), ('t102', 't999'), ('t999', 't103')]:
            with self.assertRaises(ValueError, msg=(caller, target)):
                self.host.send(caller, target, '지시', run=run)
        with self.assertRaises(ValueError):
            self.host.send('t102', 't103', '   ', run=run)
        with self.host.locked() as state:
            state['nodes']['t103']['closed_at'] = '2026-11-10T00:00:00+00:00'
            self.host.commit(state)
        with self.assertRaises(ValueError):
            self.host.send('t102', 't103', '지시', run=run)
        run.assert_not_called()

    def test_send_refuses_wrong_weekday_unless_allowed(self):
        run = self.sent()
        with patch.object(self.module, 'today_kst', return_value=TODAY):
            with self.assertRaises(ValueError):
                self.host.send('t102', 't103', '11/14(금)까지', run=run)
            run.assert_not_called()
            self.host.send('t102', 't103', '11/14(금)까지', run=run, allow_date_mismatch=True)
        run.assert_called_once()

    def test_failed_or_timed_out_send_is_recorded_once_and_never_retried(self):
        run = self.sent(stdout='', returncode=4)
        with self.assertRaises(RuntimeError) as caught:
            self.host.send('t102', 't103', '지시', run=run)
        self.assertIn('hc read t103', str(caught.exception))
        run.assert_called_once()
        timeout = Mock(side_effect=subprocess.TimeoutExpired(['hc'], 120))
        with self.assertRaises(RuntimeError):
            self.host.send('t102', 't103', '지시 2', run=timeout)
        statuses = sorted(d['status'] for d in self.host.inspect()['directives'])
        self.assertEqual(statuses, ['failed', 'uncertain'])

    def test_send_does_not_hold_the_mailbox_lock_while_hc_types(self):
        lock_path = self.host.mailbox / '.lock'
        def typing(args, **kwargs):
            with lock_path.open('a+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)   # raises if send kept the lock
                fcntl.flock(lock, fcntl.LOCK_UN)
            return subprocess.CompletedProcess(args, 0, '{"turn":1}', '')
        self.assertEqual(self.host.send('t102', 't103', '지시', run=typing)['status'], 'sent')

    def test_cli_exposes_send_and_date_override(self):
        for tail, flags in [(['send', '--help'], ('--if', '--allow-date-mismatch')),
                            (['spawn', '--help'], ('--allow-date-mismatch',))]:
            result = subprocess.run([sys.executable, str(HELPER)] + tail, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for flag in flags:
                self.assertIn(flag, result.stdout)


if __name__ == '__main__':
    unittest.main()
