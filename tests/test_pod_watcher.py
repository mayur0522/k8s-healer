import unittest
from unittest.mock import MagicMock
from src.watchers.pod_watcher import PodWatcher

class TestPodWatcher(unittest.TestCase):
    def setUp(self):
        self.core_v1 = MagicMock()
        self.watcher = PodWatcher(self.core_v1)

    def _create_mock_pod(self, container_statuses, phase="Running", deletion_timestamp=None, conditions=None):
        pod = MagicMock()
        pod.metadata.name = "test-pod"
        pod.metadata.namespace = "test-ns"
        pod.metadata.deletion_timestamp = deletion_timestamp
        pod.status.phase = phase
        pod.status.container_statuses = container_statuses
        pod.status.conditions = conditions or []
        return pod

    def _create_mock_container_status(self, waiting_reason=None, terminated_reason=None, restart_count=0, image="test-image"):
        status = MagicMock()
        status.name = "test-container"
        status.image = image
        status.restart_count = restart_count
        status.state.waiting = None
        status.last_state.terminated = None

        if waiting_reason:
            status.state.waiting = MagicMock()
            status.state.waiting.reason = waiting_reason

        if terminated_reason:
            status.last_state.terminated = MagicMock()
            status.last_state.terminated.reason = terminated_reason

        return status

    def test_crash_loop_back_off(self):
        container_status = self._create_mock_container_status(waiting_reason="CrashLoopBackOff", restart_count=5)
        pod = self._create_mock_pod([container_status])

        issues = self.watcher.check_pod_health(pod)

        self.assertEqual(len(issues), 2) # CrashLoopBackOff and HighRestarts
        self.assertEqual(issues[0]['type'], "CrashLoopBackOff")
        self.assertEqual(issues[0]['resource_name'], "test-pod")

    def test_image_pull_back_off(self):
        container_status = self._create_mock_container_status(waiting_reason="ImagePullBackOff")
        pod = self._create_mock_pod([container_status])

        issues = self.watcher.check_pod_health(pod)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['type'], "ImagePullBackOff")
        self.assertEqual(issues[0]['image'], "test-image")

    def test_oom_killed(self):
        container_status = self._create_mock_container_status(terminated_reason="OOMKilled")
        pod = self._create_mock_pod([container_status])

        issues = self.watcher.check_pod_health(pod)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['type'], "OOMKilled")

    def test_high_restarts(self):
        container_status = self._create_mock_container_status(restart_count=10)
        pod = self._create_mock_pod([container_status])

        issues = self.watcher.check_pod_health(pod)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['type'], "HighRestarts")
        self.assertEqual(issues[0]['restart_count'], 10)

    def test_pending_pod(self):
        conditions = [MagicMock()]
        conditions[0].type = "PodScheduled"
        conditions[0].status = "False"
        conditions[0].reason = "Unschedulable"
        conditions[0].message = "0/1 nodes are available"

        pod = self._create_mock_pod([], phase="Pending", conditions=conditions)

        issues = self.watcher.check_pod_health(pod)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['type'], "Pending")
        self.assertEqual(issues[0]['reason'], "Unschedulable")

    def test_healthy_pod(self):
        container_status = self._create_mock_container_status()
        pod = self._create_mock_pod([container_status])

        issues = self.watcher.check_pod_health(pod)

        self.assertEqual(len(issues), 0)

if __name__ == '__main__':
    unittest.main()
