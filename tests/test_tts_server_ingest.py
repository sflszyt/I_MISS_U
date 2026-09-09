import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
from ingest_sessions import SessionsIngestScheduler

import unittest
import threading
import time
import tempfile
from unittest import mock


class TestSessionsIngestScheduler(unittest.TestCase):

    def test_debounce_single_run(self):
        """去抖：连续调度只执行一次。"""
        runner = mock.Mock()
        with tempfile.TemporaryDirectory() as pdir, tempfile.TemporaryDirectory() as odir:
            sched = SessionsIngestScheduler(pdir, odir, delay_s=0.2, runner=runner, log=[])
            for _ in range(5):
                sched.schedule()
                time.sleep(0.02)
            time.sleep(0.6)
            self.assertEqual(runner.call_count, 1)

    def test_rerun_if_scheduled_during_run(self):
        """执行期间调度会触发补跑。"""
        count = 0
        calls = []
        state_lock = threading.Lock()

        def slow_runner():
            nonlocal count
            with state_lock:
                count += 1
                calls.append(time.time())
                first_call = (count == 1)
            if first_call:
                time.sleep(0.3)

        logs = []
        with tempfile.TemporaryDirectory() as pdir, tempfile.TemporaryDirectory() as odir:
            sched = SessionsIngestScheduler(pdir, odir, delay_s=0.05, runner=slow_runner, log=logs.append)
            # Start run_now in a background thread to simulate blocking execution
            t = threading.Thread(target=sched.run_now)
            t.start()
            # Wait for the runner to start and block
            time.sleep(0.15)
            sched.schedule()  # should trigger re-run
            t.join(timeout=2.0)
            self.assertFalse(t.is_alive())
            # Wait extra for possible re-run to finish
            time.sleep(0.2)
            self.assertEqual(count, 2)

    def test_exception_isolated(self):
        """异常被隔离，返回 False 不抛出。"""
        def boom_runner():
            raise RuntimeError('boom')

        logs = []
        with tempfile.TemporaryDirectory() as pdir, tempfile.TemporaryDirectory() as odir:
            sched = SessionsIngestScheduler(pdir, odir, delay_s=0.1, runner=boom_runner, log=logs.append)
            result = sched.run_now()
            self.assertFalse(result)
            self.assertIsNone(sched.last_success_iso)
            self.assertTrue(len(logs) > 0)

    def test_success_sets_last(self):
        """成功后记录 ISO 时间。"""
        runner = mock.Mock()
        logs = []
        with tempfile.TemporaryDirectory() as pdir, tempfile.TemporaryDirectory() as odir:
            sched = SessionsIngestScheduler(pdir, odir, delay_s=0.1, runner=runner, log=logs.append)
            result = sched.run_now()
            self.assertTrue(result)
            self.assertIsInstance(sched.last_success_iso, str)
            self.assertGreaterEqual(len(sched.last_success_iso), 19)
            self.assertIn('T', sched.last_success_iso)

    def test_serialized(self):
        """并发调度串行执行，最大并发数为一，且总调用次数等于显式调用线程数。"""
        state_lock = threading.Lock()
        max_concurrent = 0
        current_concurrent = 0
        total_calls = 0

        def counting_runner():
            nonlocal current_concurrent, max_concurrent, total_calls
            with state_lock:
                current_concurrent += 1
                total_calls += 1
                if current_concurrent > max_concurrent:
                    max_concurrent = current_concurrent
            time.sleep(0.05)
            with state_lock:
                current_concurrent -= 1

        logs = []
        with tempfile.TemporaryDirectory() as pdir, tempfile.TemporaryDirectory() as odir:
            sched = SessionsIngestScheduler(pdir, odir, delay_s=0.1, runner=counting_runner, log=logs.append)
            threads = []
            for _ in range(4):
                t = threading.Thread(target=sched.run_now)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(max_concurrent, 1)
            self.assertEqual(total_calls, 4, "并发 run_now 不应多跑（缺陷 2：4 次变 5 次）")

    def test_stale_timer_does_not_rerun(self):
        """stale timer 不应再跑一次（缺陷 1 回归防护）。"""
        count_lock = threading.Lock()
        count = 0
        first_started = threading.Event()

        def event_runner():
            nonlocal count
            with count_lock:
                count += 1
                is_first = (count == 1)
            if is_first:
                first_started.set()
                time.sleep(0.10)

        logs = []
        with tempfile.TemporaryDirectory() as pdir, tempfile.TemporaryDirectory() as odir:
            sched = SessionsIngestScheduler(pdir, odir, delay_s=0.30, runner=event_runner, log=logs.append)
            bg = threading.Thread(target=sched.run_now)
            bg.start()
            self.assertTrue(first_started.wait(timeout=2.0), "第一轮 runner 未在超时内启动")
            sched.schedule()  # 调度发生在第一轮执行期间
            bg.join(timeout=2.0)
            self.assertFalse(bg.is_alive())
            time.sleep(1.2)  # 让 timer 充分到点
            with count_lock:
                final_count = count
            self.assertEqual(final_count, 2, "stale timer 不应再跑一次（期望 2 次，实际可能是 3 次）")

    def test_run_now_returns_false_after_previous_success(self):
        """前次成功后，run_now 不应因 last_success_iso 而误判成功（缺陷 3 回归防护）。"""
        call_count = 0

        def flaky_runner():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return  # 第一次成功
            raise RuntimeError('second run fails')

        logs = []
        with tempfile.TemporaryDirectory() as pdir, tempfile.TemporaryDirectory() as odir:
            sched = SessionsIngestScheduler(pdir, odir, delay_s=0.1, runner=flaky_runner, log=logs.append)
            first_result = sched.run_now()
            self.assertTrue(first_result)
            first_success_time = sched.last_success_iso
            self.assertIsNotNone(first_success_time)
            second_result = sched.run_now()
            self.assertFalse(second_result)
            self.assertEqual(sched.last_success_iso, first_success_time, "失败后不应清空 last_success_iso")


if __name__ == '__main__':
    unittest.main()
