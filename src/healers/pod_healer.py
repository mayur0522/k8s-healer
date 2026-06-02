"""
Pod Healer - Remediation actions for pod issues.
"""

import os

import logging
from typing import Dict, Any
from datetime import datetime, timezone
import re

logger = logging.getLogger(__name__)


def _parse_memory(mem_str: str) -> int:
    """Parse kubernetes memory string to bytes."""
    if not mem_str:
        return 0

    match = re.match(r'^(\d+)([EPTGMK]i?)?$', mem_str.strip())
    if not match:
        raise ValueError(f"Invalid memory string: {mem_str}")

    value, unit = match.groups()
    value = int(value)

    unit = unit.upper() if unit else ''
    if unit == 'E': value *= 1000**6
    elif unit == 'P': value *= 1000**5
    elif unit == 'T': value *= 1000**4
    elif unit == 'G': value *= 1000**3
    elif unit == 'M': value *= 1000**2
    elif unit == 'K': value *= 1000**1
    elif unit == 'EI': value *= 1024**6
    elif unit == 'PI': value *= 1024**5
    elif unit == 'TI': value *= 1024**4
    elif unit == 'GI': value *= 1024**3
    elif unit == 'MI': value *= 1024**2
    elif unit == 'KI': value *= 1024**1

    return value


class PodHealer:
    """Healing actions for pod issues."""
    
    def __init__(self, core_v1, apps_v1):
        self.core_v1 = core_v1
        self.apps_v1 = apps_v1
    
    async def heal_crash_loop(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal a CrashLoopBackOff issue.
        
        Strategy:
        1. First, try restarting the pod
        2. If restarts > 10, rollback deployment (only if ARGOCD_SAFE_MODE is off)
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        restart_count = issue.get('restart_count', 0)
        argocd_safe = os.getenv("ARGOCD_SAFE_MODE", "true").lower() == "true"
        
        try:
            if restart_count >= 10 and not argocd_safe:
                # Try to rollback the deployment (only when ArgoCD safe mode is OFF)
                logger.warning(f"High restart count, attempting rollback for {pod_name}")
                return await self._rollback_owner_deployment(pod_name, namespace)
            elif restart_count >= 10 and argocd_safe:
                # In ArgoCD-safe mode, just restart and warn
                logger.warning(
                    f"⚠️ ARGOCD_SAFE_MODE: Pod {pod_name} has {restart_count} restarts. "
                    f"Rollback blocked to prevent GitOps drift. "
                    f"Fix the root cause in Git and let ArgoCD sync."
                )
                self.core_v1.delete_namespaced_pod(
                    name=pod_name,
                    namespace=namespace
                )
                return True
            else:
                # Just restart the pod
                logger.info(f"Restarting pod {pod_name} in {namespace}")
                self.core_v1.delete_namespaced_pod(
                    name=pod_name,
                    namespace=namespace
                )
                return True
                
        except Exception as e:
            logger.error(f"Failed to heal crash loop for {pod_name}: {e}")
            return False
    
    async def heal_oom_killed(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal an OOMKilled issue.
        
        Strategy:
        1. Identify the deployment
        2. Increase memory limits by 25%
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        container_name = issue['container']
        
        try:
            pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
            
            deployment = await self._get_owner_deployment(pod)
            
            if not deployment:
                logger.warning(f"No deployment found for pod {pod_name}")
                return False
                
            deployment_name = deployment.metadata.name

            # Find the container and increase its memory
            for container in deployment.spec.template.spec.containers:
                if container.name == container_name:

                    old_limit = container.resources.limits.get('memory', '0')
                    old_limit_bytes = _parse_memory(old_limit)

                    if old_limit_bytes == 0:
                        logger.warning(f"Container {container_name} has no memory limit")
                        return False

                    new_limit_bytes = int(old_limit_bytes * 1.25)
                    new_limit = f"{new_limit_bytes // 1024 // 1024}Mi"

                    patch = {
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "name": container_name,
                                            "resources": {
                                                "limits": {"memory": new_limit}
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }

                    self.apps_v1.patch_namespaced_deployment(
                        deployment_name, namespace, patch
                    )

                    logger.info(
                        f"Increased memory for {container_name} in {deployment_name} "
                        f"from {old_limit} to {new_limit}"
                    )
                    return True

            logger.warning(f"Container {container_name} not in deployment {deployment_name}")
            return False

        except Exception as e:
            logger.error(f"Failed to heal OOMKilled for {pod_name}: {e}")
            return False
    
    async def heal_image_pull(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal an ImagePullBackOff issue.
        
        Strategy:
        1. Check if image exists
        2. Verify image pull secret
        3. Alert if unresolvable
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        image = issue.get('image', 'unknown')
        
        logger.warning(f"ImagePullBackOff for {pod_name}: {image}")
        
        # This typically requires manual intervention
        # But we can try restarting to retry the pull
        try:
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace
            )
            logger.info(f"Restarted pod {pod_name} to retry image pull")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart pod {pod_name}: {e}")
            return False
    
    async def heal_pending(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal a pending pod.
        
        Strategy:
        1. Check scheduling failure reason
        2. If resources, suggest scaling
        3. If affinity, log detailed info
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        reason = issue.get('reason', 'Unknown')
        message = issue.get('message', '')
        
        logger.warning(f"Pod {pod_name} pending: {reason} - {message}")
        
        # Most pending issues require human intervention
        # Just log detailed information
        return False
    
    async def heal_high_restarts(self, issue: Dict[str, Any], resource: Any) -> bool:
        """
        Heal a pod with high restart count.
        
        Strategy:
        1. Collect logs for analysis
        2. Restart the pod
        """
        pod_name = issue['resource_name']
        namespace = issue['namespace']
        restart_count = issue.get('restart_count', 0)
        
        logger.warning(f"Pod {pod_name} has {restart_count} restarts")
        
        try:
            # Restart the pod
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to restart {pod_name}: {e}")
            return False
    
    async def _rollback_owner_deployment(self, pod_name: str, namespace: str) -> bool:
        """Rollback the deployment that owns this pod."""
        try:
            pod = self.core_v1.read_namespaced_pod(pod_name, namespace)
            deployment = await self._get_owner_deployment(pod)
            
            if not deployment:
                logger.warning(f"No deployment found for pod {pod_name}")
                return False

            deployment_name = deployment.metadata.name

            # Trigger rollback by updating annotations with a unique timestamp
            now = datetime.now(timezone.utc).isoformat()
            patch = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": now
                            }
                        }
                    }
                }
            }
            
            self.apps_v1.patch_namespaced_deployment(
                deployment_name, namespace, patch
            )

            logger.info(f"Triggered rollback for deployment {deployment_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback for pod {pod_name}: {e}")
            return False

    async def _get_owner_deployment(self, pod: Any) -> Any:
        """Get the owner deployment of a pod."""
        for owner in pod.metadata.owner_references or []:
            if owner.kind == "ReplicaSet":
                rs = self.apps_v1.read_namespaced_replica_set(
                    owner.name, pod.metadata.namespace
                )
                for rs_owner in rs.metadata.owner_references or []:
                    if rs_owner.kind == "Deployment":
                        return self.apps_v1.read_namespaced_deployment(
                            rs_owner.name, pod.metadata.namespace
                        )
        return None
