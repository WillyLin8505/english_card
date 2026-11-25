"""PrioritySlots: batch (background) model calls wait while a learner's photo runs (card 1405 / #1842)."""
import threading
import time
import unittest

from inference_control import PrioritySlots


class PrioritySlotsTest(unittest.TestCase):
    def _run_in_thread(self, slots, background, started, release):
        def work():
            with slots.request(background=background), slots.slot():
                started.set()
                release.wait(5)
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread

    def test_background_waits_while_interactive_running(self):
        slots = PrioritySlots(4)
        interactive_started, release_interactive = threading.Event(), threading.Event()
        self._run_in_thread(slots, False, interactive_started, release_interactive)
        self.assertTrue(interactive_started.wait(2))

        background_started, release_background = threading.Event(), threading.Event()
        self._run_in_thread(slots, True, background_started, release_background)
        # Plenty of free slots, but a learner's photo is running: no new batch call starts.
        self.assertFalse(background_started.wait(0.3))

        release_interactive.set()
        self.assertTrue(background_started.wait(2))
        release_background.set()

    def test_interactive_is_not_blocked_by_background(self):
        slots = PrioritySlots(2)
        background_started, release_background = threading.Event(), threading.Event()
        self._run_in_thread(slots, True, background_started, release_background)
        self.assertTrue(background_started.wait(2))

        interactive_started, release_interactive = threading.Event(), threading.Event()
        self._run_in_thread(slots, False, interactive_started, release_interactive)
        self.assertTrue(interactive_started.wait(2))
        release_interactive.set()
        release_background.set()

    def test_counters_return_to_zero(self):
        slots = PrioritySlots(3)
        for background in (True, False, False, True):
            with slots.request(background=background), slots.slot():
                pass
        self.assertEqual((slots.active, slots.background_active,
                          slots.interactive_active, slots.interactive_waiting), (0, 0, 0, 0))


if __name__ == '__main__':
    unittest.main()
