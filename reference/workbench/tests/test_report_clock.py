"""B16 a report's header time must not run ahead of when it is sent (2026-11-11)."""
from pathlib import Path
from unittest.mock import patch
import unittest
import test_bench


def utc(kst_hhmm):
    """2026-11-11 HH:MM KST as the ISO UTC string now() returns."""
    hour, minute = map(int, kst_hhmm.split(':'))
    return f'2026-11-11T{hour - 9:02d}:{minute:02d}:00+00:00'


class ReportClock(unittest.TestCase):
    spawn = test_bench.HostContract.spawn

    def setUp(self):
        test_bench.HostContract.setUp(self)
        self.spawn('secretary', 'operator', 't101')
        self.spawn('lead', 't101', 't102')

    def report(self, sent, summary, **kw):
        with patch.object(self.module, 'now', return_value=utc(sent)):
            return self.host.report('t102', summary, **kw)

    def test_todays_three_slips(self):
        # t2m wrote 13:20 at 13:13 and 13:50 at 13:26: both refused, with the send time in the message.
        with self.assertRaisesRegex(ValueError, r"'13:20' reads as 13:20, 7 minutes after the send time 13:13"):
            self.report('13:13', '[프로젝트 리드 t2m · 11/11 13:20 중간 보고 · 회신 필요 없음] 본문')
        with self.assertRaisesRegex(ValueError, r'13:26 KST'):
            self.report('13:26', '[프로젝트 리드 t2m · 11/11 13:50 · 운영자 지시(13:20)] 본문')
        # t1z wrote 15:5x at 15:46. 'x' reads as its earliest value, 15:50: 4 minutes, inside the 5-minute slack.
        sent = self.report('15:46', '[리뷰에이전트 리드 t1z · 15:5x KST] 본문')
        self.assertEqual(sent['sent_kst'], '11/11(수) 15:46 KST')
        self.assertEqual(self.module.late_header_times('[x · 15:5x KST]', utc('15:44'))[0]['read_as'], '15:50')

    def test_past_times_quotes_plans_and_other_days_pass(self):
        for summary in [
            '[작업대 개선 리드 t3b, 첫 보고 (11/10 18:00 기한)] 본문',              # other day and a deadline
            '[운영자 직접 지시] 분석 · 범위 _my · 끝낼 시각 17:30 KST',            # R1 line names when it will end
            '[보고] 15:10쯤 main에 반영합니다',                                  # a plan
            '[정정] 머리의 "09:5x KST"는 틀렸고 실제로는 09:41이다',              # a quoted wrong time
            '[보고] 집계 기준 2026-11-08T15:00Z 이후',                            # a UTC stamp
            '[보고 15:30 KST] 본문',                                              # earlier than sent: fine
            '[보고] 11/12 16:40 재수집 예정',                                      # another day
            '[CI 리드 수신] 1차 보고 11/12(목) 저녁(17:43 예약)',                   # a booking
            '[보고] 17:30 첫 보고에 결과를 냅니다',                                # more than 90 minutes ahead
        ]:
            self.report('15:30', summary)

    def test_only_the_first_line_is_checked_and_the_override_is_explicit(self):
        self.report('10:00', '[보고 10:00]\n본문 속 예정 12:30, 사건 13:00 같은 시각은 보지 않는다')
        with self.assertRaises(ValueError):
            self.report('10:00', '[보고 10:20] 본문')
        sent = self.report('10:00', '[보고 10:20] 본문', allow_late_time=True)
        self.assertEqual(sent['sent_kst'], '11/11(수) 10:00 KST')

    def test_retry_of_a_stored_report_is_not_rechecked(self):
        first = self.report('10:00', '[보고 10:03] 본문', report_id='r-same')
        again = self.report('10:30', '[보고 10:03] 본문', report_id='r-same')
        self.assertEqual(again['created_at'], first['created_at'])

    def test_mcp_report_tool_lists_the_override(self):
        source = Path(self.module.__file__).read_text()
        self.assertIn("'allow_late_time': {'type': 'boolean'}", source)
        self.assertIn("'bench_report': {'summary', 'complete', 'report_id', 'allow_late_time'}", source)

if __name__ == '__main__':
    unittest.main()
