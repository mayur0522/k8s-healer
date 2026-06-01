import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

from src.healers.pod_healer import PodHealer, _parse_memory


class TestPodHealer(unittest.TestCase):

    def setUp(self):
        self.core_v1 = MagicMock()
        self.apps_v1 = MagicMock()
        self.healer = PodHealer(self.core_v1, self.apps_v1)

        # Make async functions awaitable
        self.healer._get_owner_deployment = AsyncMock()

    def test_parse_memory(self):
        self.assertEqual(_parse_memory("1Gi"), 1024**3)
        self.assertEqual(_parse_memory("500Mi"), 500 * 1024**2)
        self.assertEqual(_parse_memory("2G"), 2 * 1000**3)
        self.assertEqual(_parse_memory("10K"), 10 * 1000)
        with self.assertRaises(ValueError):
            _parse_memory("1.5Gi")

    def test_heal_oom_killed_increases_memory(self):
        # Mocks
        pod = MagicMock()
        deployment = MagicMock()
        deployment.metadata.name = "test-deployment"

        container = MagicMock()
        container.name = "test-container"
        container.resources.limits = {'memory': '100Mi'}
        deployment.spec.template.spec.containers = [container]

        self.core_v1.read_namespaced_pod.return_value = pod
        self.healer._get_owner_deployment.return_value = deployment
        self.apps_v1.patch_namespaced_deployment = MagicMock()

        issue = {
            "resource_name": "test-pod",
            "namespace": "test-ns",
            "container": "test-container"
        }

        # Run
        result = asyncio.run(self.healer.heal_oom_killed(issue, None))

        # Assert
        self.assertTrue(result)
        self.apps_v1.patch_namespaced_deployment.assert_called_once()
        args, _ = self.apps_v1.patch_namespaced_deployment.call_args

        patched_deployment_name = args[0]
        patched_namespace = args[1]
        patch_body = args[2]

        self.assertEqual(patched_deployment_name, "test-deployment")
        self.assertEqual(patched_namespace, "test-ns")

        new_memory_limit = patch_body['spec']['template']['spec']['containers'][0]['resources']['limits']['memory']
        self.assertEqual(new_memory_limit, '125Mi')

    def test_rollback_owner_deployment(self):
        # Mocks
        pod = MagicMock()
        deployment = MagicMock()
        deployment.metadata.name = "test-deployment"

        self.core_v1.read_namespaced_pod.return_value = pod
        self.healer._get_owner_deployment.return_value = deployment
        self.apps_v1.patch_namespaced_deployment = MagicMock()

        # Run
        result = asyncio.run(self.healer._rollback_owner_deployment("test-pod", "test-ns"))

        # Assert
        self.assertTrue(result)
        self.apps_v1.patch_namespaced_deployment.assert_called_once()
        args, _ = self.apps_v1.patch_namespaced_deployment.call_args
        self.assertIn("kubectl.kubernetes.io/restartedAt", args[2]['spec']['template']['metadata']['annotations'])

if __name__ == '__main__':
    unittest.main()
