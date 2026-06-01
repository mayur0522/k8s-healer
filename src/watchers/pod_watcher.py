"""
Pod Watcher - Monitors pod health and detects issues.
"""

import logging
from typing import List, Dict, Any

from kubernetes.client import V1Pod

logger = logging.getLogger(__name__)


class PodWatcher:
    """Watches pods for health issues."""
    
    def __init__(self, core_v1):
        self.core_v1 = core_v1
        self.restart_threshold = 5
    
    def check_pod_health(self, pod: V1Pod) -> List[Dict[str, Any]]:
        """
        Check a pod for health issues.
        
        Returns:
            List of detected issues
        """
        issues = []
        
        # Skip if pod is being deleted
        if pod.metadata.deletion_timestamp:
            return issues
        
        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace
        
        # Check container statuses
        if pod.status.container_statuses:
            for container in pod.status.container_statuses:
                # Check for CrashLoopBackOff
                if container.state.waiting:
                    reason = container.state.waiting.reason
                    
                    if reason == "CrashLoopBackOff":
                        issues.append({
                            "type": "CrashLoopBackOff",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "container": container.name,
                            "restart_count": container.restart_count,
                            "message": f"Container {container.name} in CrashLoopBackOff"
                        })
                    
                    elif reason == "ImagePullBackOff":
                        issues.append({
                            "type": "ImagePullBackOff",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "container": container.name,
                            "image": container.image,
                            "message": f"Failed to pull image {container.image}"
                        })
                
                # Check for OOMKilled
                if container.last_state.terminated:
                    if container.last_state.terminated.reason == "OOMKilled":
                        issues.append({
                            "type": "OOMKilled",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "container": container.name,
                            "message": f"Container {container.name} was OOMKilled"
                        })
                
                # Check high restart count
                if container.restart_count >= self.restart_threshold:
                    issues.append({
                        "type": "HighRestarts",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "container": container.name,
                        "restart_count": container.restart_count,
                        "message": f"Container {container.name} has {container.restart_count} restarts"
                    })
        
        # Check pod phase
        if pod.status.phase == "Pending":
            # Check how long it's been pending
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    if condition.type == "PodScheduled" and condition.status == "False":
                        issues.append({
                            "type": "Pending",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "reason": condition.reason,
                            "message": condition.message or "Pod cannot be scheduled"
                        })
        
        return issues
    
    def get_pod_logs(self, pod_name: str, namespace: str, container: str = None, tail: int = 50) -> str:
        """Get logs from a pod."""
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                tail_lines=tail
            )
            return logs
        except Exception as e:
            logger.error(f"Failed to get logs for {pod_name}: {e}")
            return ""
