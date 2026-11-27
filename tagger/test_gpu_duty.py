"""GpuDuty: background model calls leave the GPU idle part of the time (owner 11/06)."""
import unittest
import threading

from inference_control import GpuDuty


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s
        self.slept += s


class GpuDutyTest(unittest.TestCase):
    def make(self, duty):
        c = FakeClock()
        return GpuDuty(duty, clock=c, sleep=c.sleep), c

    def call(self, g, c, seconds, wait=True):
        with g.run(wait=wait):
            c.t += seconds

    def test_back_to_back_background_calls_rest_between(self):
        g, c = self.make(0.6)
        for _ in range(10):
            self.call(g, c, 6.0)
        busy = 60.0
        self.assertAlmostEqual(busy / c.t, 0.6, delta=0.05)  # GPU busy ~60 % of the time

    def test_interactive_call_never_waits_but_counts(self):
        g, c = self.make(0.5)
        self.call(g, c, 4.0)
        self.call(g, c, 1.0, wait=False)
        self.assertEqual(c.slept, 0.0)
        self.assertGreater(g.wait_s(), 0.0)

    def test_duty_one_is_off(self):
        g, c = self.make(1)
        for _ in range(5):
            self.call(g, c, 3.0)
        self.assertEqual(c.slept, 0.0)


if __name__ == "__main__":
    unittest.main()


class ForegroundHoldTest(unittest.TestCase):
    """問題回報 #1842: a learner's photo keeps new background calls from starting."""

    def test_background_waits_while_a_photo_is_tagged(self):
        c = FakeClock()
        g = GpuDuty(1.0, clock=c, sleep=c.sleep)
        g.foreground = 1          # a photo call is running
        g.foreground_hold_s = 3.0
        with g.run(wait=True):
            pass
        self.assertGreaterEqual(c.slept, 3.0)  # held, but never longer than the cap

    def test_foreground_counts_itself_and_never_waits(self):
        c = FakeClock()
        g = GpuDuty(1.0, clock=c, sleep=c.sleep)
        g.foreground = 1
        with g.run(wait=False):
            self.assertEqual(g.foreground, 2)
        self.assertEqual(g.foreground, 1)
        self.assertEqual(c.slept, 0.0)


class ConcurrentDutyTest(unittest.TestCase):
    def test_background_waits_for_active_call_and_its_rest(self):
        c = FakeClock()
        g = GpuDuty(0.5, clock=c, sleep=c.sleep)
        attempted = threading.Event()
        entered = threading.Event()
        starts = []

        def second():
            attempted.set()
            with g.run():
                starts.append(c.t)
                entered.set()

        with g.run():
            worker = threading.Thread(target=second)
            worker.start()
            self.assertTrue(attempted.wait(1))
            overlapped = entered.wait(0.05)
            # Interactive work must still bypass background pacing.
            with g.run(wait=False):
                c.t += 0.25
            c.t += 0.75
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertFalse(overlapped)
        self.assertGreaterEqual(starts[0], 2.0)

    def test_failed_background_call_releases_lane_and_accounts_rest(self):
        c = FakeClock()
        g = GpuDuty(0.5, clock=c, sleep=c.sleep)
        with self.assertRaises(ValueError):
            with g.run():
                c.t += 1
                raise ValueError('model failed')
        with g.run():
            self.assertEqual(c.t, 2)
