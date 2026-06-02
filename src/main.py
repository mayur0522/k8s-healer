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
        
        # ArgoCD-safe mode: disable healers that patch deployments (prevents GitOps drift)
        self.argocd_safe_mode = os.getenv("ARGOCD_SAFE_MODE", "true").lower() == "true"
        
        # Token budget: limit AI API calls per hour to control costs
        self.max_ai_calls_per_hour = int(os.getenv("MAX_AI_CALLS_PER_HOUR", "30"))
        self.ai_calls_this_hour: list = []  # timestamps of AI calls
        self.total_ai_calls = 0
        
        # State tracking
        self.action_cooldowns: Dict[str, datetime] = {}
        self.cooldown_seconds = int(os.getenv("COOLDOWN_SECONDS", "300"))
        
        logger.info(f"K8sHealer initialized (dry_run={self.dry_run}, argocd_safe={self.argocd_safe_mode}, max_ai_calls/hr={self.max_ai_calls_per_hour})")
    
    async def run(self):
        """Main run loop."""
        logger.info("🚀 Starting K8sHealer...")
        
        # Run watchers concurrently
        await asyncio.gather(
            self.watch_pods(),
            self.watch_events(),
            self.periodic_health_check(),
            self.log_token_usage()
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
    
    def _check_ai_budget(self) -> bool:
        """Check if we're within the AI API call budget for this hour."""
        now = datetime.now()
        # Remove calls older than 1 hour
        self.ai_calls_this_hour = [
            t for t in self.ai_calls_this_hour
            if (now - t).total_seconds() < 3600
        ]
        
        if len(self.ai_calls_this_hour) >= self.max_ai_calls_per_hour:
            logger.warning(
                f"💰 AI budget limit reached: {len(self.ai_calls_this_hour)}/{self.max_ai_calls_per_hour} calls this hour. "
                f"Skipping AI analysis to control costs."
            )
            return False
        return True
    
    async def log_token_usage(self):
        """Periodically log AI token usage stats for cost monitoring."""
        while True:
            await asyncio.sleep(3600)  # Every hour
            calls_this_hour = len(self.ai_calls_this_hour)
            logger.info(
                f"💰 TOKEN USAGE REPORT: "
                f"AI calls this hour: {calls_this_hour}/{self.max_ai_calls_per_hour} | "
                f"Total AI calls since start: {self.total_ai_calls} | "
                f"Est. tokens used this hour: ~{calls_this_hour * 600}"
            )
    
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
        
        # Get AI analysis if enabled AND within budget
        if os.getenv("AZURE_OPENAI_API_KEY") and self._check_ai_budget():
            analysis = await self.ai_analyzer.analyze_issue(issue, resource)
            self.ai_calls_this_hour.append(datetime.now())
            self.total_ai_calls += 1
            logger.info(
                f"🤖 AI Analysis: {analysis.get('summary', 'N/A')} "
                f"[calls this hour: {len(self.ai_calls_this_hour)}/{self.max_ai_calls_per_hour}]"
            )
        
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
        """Execute a healing action based on issue type.
        
        In ArgoCD-safe mode, only pod-level actions (restarts) are allowed.
        Deployment-level patches (memory increase, rollback) are BLOCKED
        to prevent GitOps drift.
        """
        issue_type = issue['type']
        
        # ArgoCD-safe mode: block healers that patch Deployments
        if self.argocd_safe_mode and issue_type in ('OOMKilled',):
            logger.warning(
                f"⚠️ ARGOCD_SAFE_MODE: Skipping {issue_type} healer for {issue.get('resource_name')} — "
                f"this would patch the Deployment and cause ArgoCD drift. "
                f"Set ARGOCD_SAFE_MODE=false to allow deployment patches."
            )
            return False
        
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
