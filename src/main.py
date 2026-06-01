"""
Kubernetes K8sHealer - Main Controller
Watches for issues and automatically remediates them.
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException

from watchers.pod_watcher import PodWatcher
from watchers.event_watcher import EventWatcher
from healers.pod_healer import PodHealer
from ai.analyzer import AIAnalyzer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class K8sHealerController:
    """Main controller for K8sHealer."""
    
    def __init__(self):
        # Load Kubernetes config
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded local Kubernetes config")
        
        # Initialize Kubernetes clients
        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        
        # Initialize components
        self.pod_watcher = PodWatcher(self.core_v1)
        self.event_watcher = EventWatcher(self.core_v1)
        self.pod_healer = PodHealer(self.core_v1, self.apps_v1)
        self.ai_analyzer = AIAnalyzer()
        
        # Configuration
        self.excluded_namespaces = os.getenv(
            "EXCLUDED_NAMESPACES", 
            "kube-system,kube-public,k8s-healer"
        ).split(",")
        
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        
        # State tracking
        self.action_cooldowns: Dict[str, datetime] = {}
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        
        logger.info(f"K8sHealer initialized (dry_run={self.dry_run})")
    
    async def run(self):
        """Main run loop."""
        logger.info("🚀 Starting K8sHealer...")
        
        # Run watchers concurrently
        await asyncio.gather(
            self.watch_pods(),
            self.watch_events(),
            self.periodic_health_check()
        )
    
    async def watch_pods(self):
        """Watch for problematic pods."""
        logger.info("👀 Starting pod watcher...")
        
        w = watch.Watch()
        
        while True:
            try:
                for event in w.stream(
                    self.core_v1.list_pod_for_all_namespaces,
                    timeout_seconds=60
                ):
                    await self.handle_pod_event(event)
                    
            except ApiException as e:
                logger.error(f"API error in pod watcher: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error in pod watcher: {e}")
                await asyncio.sleep(5)
    
    async def watch_events(self):
        """Watch Kubernetes events for issues."""
        logger.info("📨 Starting event watcher...")
        
        w = watch.Watch()
        
        while True:
            try:
                for event in w.stream(
                    self.core_v1.list_event_for_all_namespaces,
                    timeout_seconds=60
                ):
                    await self.handle_k8s_event(event)
                    
            except ApiException as e:
                logger.error(f"API error in event watcher: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error in event watcher: {e}")
                await asyncio.sleep(5)
    
    async def periodic_health_check(self):
        """Periodic health check for all pods."""
        while True:
            await asyncio.sleep(60)  # Every minute
            
            try:
                pods = self.core_v1.list_pod_for_all_namespaces()
                
                for pod in pods.items:
                    if pod.metadata.namespace in self.excluded_namespaces:
                        continue
                    
                    issues = self.pod_watcher.check_pod_health(pod)
                    
                    for issue in issues:
                        await self.handle_issue(issue, pod)
                        
            except Exception as e:
                logger.error(f"Error in health check: {e}")
    
    async def handle_pod_event(self, event: dict):
        """Handle a pod watch event."""
        event_type = event['type']
        pod = event['object']
        
        if pod.metadata.namespace in self.excluded_namespaces:
            return
        
        if event_type in ['ADDED', 'MODIFIED']:
            issues = self.pod_watcher.check_pod_health(pod)
            
            for issue in issues:
                await self.handle_issue(issue, pod)
    
    async def handle_k8s_event(self, event: dict):
        """Handle a Kubernetes event."""
        k8s_event = event['object']
        
        if k8s_event.involved_object.namespace in self.excluded_namespaces:
            return
        
        # Look for warning events
        if k8s_event.type == "Warning":
            issue = self.event_watcher.analyze_event(k8s_event)
            
            if issue:
                await self.handle_issue(issue, k8s_event)
    
    async def handle_issue(self, issue: dict, resource: Any):
        """Handle a detected issue."""
        issue_key = f"{issue['type']}:{issue.get('resource_name', 'unknown')}"
        
        # Check cooldown
        if issue_key in self.action_cooldowns:
            last_action = self.action_cooldowns[issue_key]
            if (datetime.now() - last_action).seconds < self.cooldown_seconds:
                logger.debug(f"Skipping {issue_key} (cooldown)")
                return
        
        logger.warning(f"🔍 Issue detected: {issue['type']} - {issue.get('message', '')}")
        
        # Get AI analysis if enabled
        if os.getenv("GEMINI_API_KEY"):
            analysis = await self.ai_analyzer.analyze_issue(issue, resource)
            logger.info(f"🤖 AI Analysis: {analysis.get('summary', 'N/A')}")
        
        # Execute healing action
        if not self.dry_run:
            success = await self.execute_healing(issue, resource)
            
            if success:
                self.action_cooldowns[issue_key] = datetime.now()
                logger.info(f"✅ Healing action completed for {issue_key}")
            else:
                logger.error(f"❌ Healing action failed for {issue_key}")
        else:
            logger.info(f"🔸 DRY RUN: Would heal {issue_key}")
    
    async def execute_healing(self, issue: dict, resource: Any) -> bool:
        """Execute a healing action based on issue type."""
        issue_type = issue['type']
        
        healers = {
            'CrashLoopBackOff': self.pod_healer.heal_crash_loop,
            'OOMKilled': self.pod_healer.heal_oom_killed,
            'ImagePullBackOff': self.pod_healer.heal_image_pull,
            'Pending': self.pod_healer.heal_pending,
            'HighRestarts': self.pod_healer.heal_high_restarts,
        }
        
        healer = healers.get(issue_type)
        
        if healer:
            return await healer(issue, resource)
        else:
            logger.warning(f"No healer for issue type: {issue_type}")
            return False


async def main():
    """Main entry point."""
    controller = K8sHealerController()
    await controller.run()


if __name__ == "__main__":
    asyncio.run(main())
