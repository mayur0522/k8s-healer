"""
AI Analyzer - Uses Azure OpenAI for root cause analysis.
"""

import os
import json
import logging
from typing import Dict, Any

from openai import AzureOpenAI

logger = logging.getLogger(__name__)

# Initialize Azure OpenAI
api_key = os.getenv("AZURE_OPENAI_API_KEY")
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
deployment = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o")


class AIAnalyzer:
    """AI-powered issue analysis using Azure OpenAI."""
    
    def __init__(self):
        if api_key and endpoint:
            self.client = AzureOpenAI(
                api_key=api_key,
                api_version="2024-02-15-preview",
                azure_endpoint=endpoint,
            )
            self.deployment = deployment
            self.enabled = True
            logger.info(f"AI analysis enabled (deployment={self.deployment})")
        else:
            self.client = None
            self.enabled = False
            logger.warning("AI analysis disabled - no AZURE_OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT")
    
    async def analyze_issue(self, issue: Dict[str, Any], resource: Any) -> Dict[str, Any]:
        """
        Analyze an issue using AI.
        
        Returns:
            Analysis with summary and recommendations
        """
        if not self.enabled:
            return {"summary": "AI analysis disabled"}
        
        try:
            prompt = self._build_prompt(issue, resource)
            
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a Kubernetes SRE expert. Analyze issues and respond ONLY with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
                max_tokens=500,
            )
            
            return self._parse_response(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return {"summary": "Analysis failed", "error": str(e)}
    
    def _build_prompt(self, issue: Dict[str, Any], resource: Any) -> str:
        """Build the analysis prompt."""
        return f"""Analyze this Kubernetes issue and provide a brief assessment.

ISSUE:
- Type: {issue.get('type')}
- Resource: {issue.get('resource_name')}
- Namespace: {issue.get('namespace')}
- Message: {issue.get('message', 'N/A')}

Provide a JSON response:
{{
    "summary": "One sentence summary",
    "likely_cause": "What probably caused this",
    "recommended_action": "What to do",
    "severity": "low|medium|high|critical"
}}
"""
    
    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse AI response."""
        try:
            if "```json" in text:
                json_str = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                json_str = text.split("```")[1].split("```")[0]
            else:
                json_str = text
            
            return json.loads(json_str.strip())
        except:
            return {"summary": text[:200]}
