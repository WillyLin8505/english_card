"""GpuDuty: background model calls leave the GPU idle part of the time (owner 11/06)."""
import unittest

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
