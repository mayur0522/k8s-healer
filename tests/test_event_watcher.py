import unittest
from unittest.mock import MagicMock
from src.watchers.event_watcher import EventWatcher

class TestEventWatcher(unittest.TestCase):
    def setUp(self):
        self.core_v1 = MagicMock()
        self.watcher = EventWatcher(self.core_v1)

    def _create_mock_event(self, reason, message, name="test-resource", namespace="test-ns", kind="Pod"):
        event = MagicMock()
        event.reason = reason
        event.message = message
        event.involved_object.name = name
        event.involved_object.namespace = namespace
        event.involved_object.kind = kind
        event.count = 1
        return event

    def test_failed_scheduling_event(self):
        event = self._create_mock_event("FailedScheduling", "0/1 nodes are available")
        issue = self.watcher.analyze_event(event)

        self.assertIsNotNone(issue)
        self.assertEqual(issue['type'], "Pending")
        self.assertEqual(issue['reason'], "FailedScheduling")

    def test_oom_killed_event(self):
        event = self._create_mock_event("SomeReason", "Container was OOMKilled")
        issue = self.watcher.analyze_event(event)

        self.assertIsNotNone(issue)
        self.assertEqual(issue['type'], "OOMKilled")

    def test_normal_event(self):
        event = self._create_mock_event("SuccessfulCreate", "Created pod test-pod")
        issue = self.watcher.analyze_event(event)

        self.assertIsNone(issue)

if __name__ == '__main__':
    unittest.main()
