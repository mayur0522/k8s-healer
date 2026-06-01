"""
AI Analyzer - Uses AI for root cause analysis.
"""

import os
import json
import logging
from typing import Dict, Any

import google.generativeai as genai

logger = logging.getLogger(__name__)

# Initialize Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)


class AIAnalyzer:
    """AI-powered issue analysis."""
    
    def __init__(self):
        if api_key:
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            self.enabled = True
        else:
            self.enabled = False
            logger.warning("AI analysis disabled - no GEMINI_API_KEY")
    
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
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=500,
                )
            )
            
            return self._parse_response(response.text)
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return {"summary": "Analysis failed", "error": str(e)}
    
    def _build_prompt(self, issue: Dict[str, Any], resource: Any) -> str:
        """Build the analysis prompt."""
        return f"""You are a Kubernetes SRE expert. Analyze this issue and provide a brief assessment.

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
