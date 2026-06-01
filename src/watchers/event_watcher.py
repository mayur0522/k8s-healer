"""
Event Watcher - Analyzes Kubernetes events.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class EventWatcher:
    """Analyzes Kubernetes events for issues."""
    
    def __init__(self, core_v1):
        self.core_v1 = core_v1
        
        # Event patterns to watch for
        self.warning_patterns = {
            "FailedScheduling": "Pending",
            "FailedMount": "MountFailure",
            "FailedAttachVolume": "VolumeFailure",
            "Unhealthy": "ProbeFailure",
            "BackOff": "CrashLoopBackOff",
            "FailedCreate": "CreateFailure",
            "EvictionThresholdMet": "DiskPressure",
        }
    
    def analyze_event(self, event) -> Optional[Dict[str, Any]]:
        """
        Analyze a Kubernetes event.
        
        Returns:
            Issue dict if actionable, None otherwise
        """
        reason = event.reason
        
        if reason in self.warning_patterns:
            return {
                "type": self.warning_patterns[reason],
                "resource_name": event.involved_object.name,
                "namespace": event.involved_object.namespace,
                "resource_kind": event.involved_object.kind,
                "reason": reason,
                "message": event.message,
                "count": event.count or 1,
            }
        
        # Check for OOMKilled in event message
        if event.message and "OOMKilled" in event.message:
            return {
                "type": "OOMKilled",
                "resource_name": event.involved_object.name,
                "namespace": event.involved_object.namespace,
                "message": event.message,
            }
        
        return None
