"""
Uses OpenAI Responses API to analyze contracts and detect risks.
"""

import os
import json
import time
import logging
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
from enum import Enum
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Import OpenAI client (Responses API)
from openai import OpenAI

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RedFlag:
    clause_text: str
    risk_type: str
    explanation: str
    why_risky: str
    suggested_alternative: str
    severity: RiskLevel


@dataclass
class RiskScore:
    financial_risk: RiskLevel
    legal_exposure: RiskLevel
    fairness: RiskLevel
    missing_clauses: RiskLevel
    overall_score: RiskLevel


@dataclass
class ContractAnalysis:
    summary: str
    key_terms: Dict[str, str]
    red_flags: List[RedFlag]
    risk_score: RiskScore
    recommendations: List[str]
    processing_time: float


class ContractAnalyzer:
    """
    AI-powered contract analyzer using OpenAI Responses API.
    """

    def __init__(self, api_key: str, model: str = "gpt-4.1", timeout_seconds: int = 60):
        """
        Initialize the analyzer.

        Args:
            api_key: OpenAI API key (string)
            model: Model name (default 'gpt-4.1')
            timeout_seconds: HTTP timeout for requests
        """
        if not api_key:
            raise ValueError("api_key is required to initialize ContractAnalyzer")
        # Initialize client
        self.client = OpenAI(api_key=api_key)
        self.model_name = model 
        self.timeout_seconds = timeout_seconds
        logger.info(f"ContractAnalyzer initialized with model: {model}")

    def analyze(self, contract_text: str) -> ContractAnalysis:
        start_time = time.time()
        logger.info(f"Starting contract analysis ({len(contract_text)} chars)")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(contract_text)

        logger.info("Calling Responses API for analysis...")
        raw_response = self._call_gpt(system_prompt, user_prompt)

        logger.info("Parsing AI response...")
        parsed = self._parse_response(raw_response)

        analysis = self._create_analysis_object(parsed)
        analysis.processing_time = time.time() - start_time

        logger.info(f"Analysis complete in {analysis.processing_time:.2f}s - {len(analysis.red_flags)} red flags")
        return analysis

    def _build_system_prompt(self) -> str:
        return (
            "You are an expert contract reviewer and legal analyst specializing in identifying risks, "
            "unfair terms, and red flags in legal agreements. Use plain English and provide actionable suggestions."
        )

    def _build_user_prompt(self, contract_text: str) -> str:
        return f"""Analyze this contract and provide a comprehensive risk assessment.

CONTRACT TEXT:
{contract_text}

Provide your analysis in the following JSON format (must be valid JSON):

{{
    "summary": "Brief 2-3 sentence summary of what this contract is about and its main purpose",
    "key_terms": {{
        "parties": "Who are the parties involved",
        "effective_date": "When does it start (or 'Not specified')",
        "duration": "How long does it last",
        "payment_terms": "Payment structure and amounts (or 'Not specified')",
        "main_obligations": "Key responsibilities of each party",
        "termination": "How can it be ended"
    }},
    "red_flags": [
        {{
            "clause_text": "Exact text of the problematic clause (max 100 words)",
            "risk_type": "Type of risk (e.g., 'Hidden Penalty', 'Auto-Renewal Trap', 'One-Sided Obligation')",
            "explanation": "What this clause means in simple English (2-3 sentences)",
            "why_risky": "Why this is dangerous or unfair to the user (2-3 sentences)",
            "suggested_alternative": "Better, fairer wording for this clause",
            "severity": "high/medium/low"
        }}
    ],
    "risk_score": {{
        "financial_risk": "high/medium/low",
        "legal_exposure": "high/medium/low",
        "fairness": "high/medium/low",
        "missing_clauses": "high/medium/low",
        "overall_score": "high/medium/low"
    }},
    "recommendations": [
        "Specific action the user should take (e.g., 'Negotiate a 30-day cancellation window')"
    ]
}}

CRITICAL: Return ONLY valid JSON. No markdown, no code blocks, no explanations outside the JSON.
"""

    def _call_gpt(self, system_prompt: str, user_prompt: str) -> Any:
        """
        Uses the Responses API to create a response. Returns the raw response object.
        """
        try:
            response = self.client.responses.create(
                model=self.model_name,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_output_tokens=1200
            )
            return response
        except Exception as e:
            logger.exception("Failed to call OpenAI Responses API")
            raise RuntimeError(f"AI analysis failed: {e}")

    def _extract_text_from_response(self, response: Any) -> str:
        """
        Robust extraction of textual output from Responses API object.
        Tries response.output_text, then response.output[*].content[*]['text'] or 'content' fields.
        """
        # Try the convenience property first
        try:
            text = getattr(response, "output_text", None)
            if text:
                return text
        except Exception:
            pass

        # Fallback: inspect response.output
        try:
            output = getattr(response, "output", None) or response.get("output", None)
            if not output:
                # last resort: convert response to dict and search
                resp_dict = json.loads(response.json()) if hasattr(response, "json") else {}
                output = resp_dict.get("output", [])
            # Aggregate text pieces
            parts = []
            for item in output:
                # item may have 'content' list
                content_list = item.get("content") if isinstance(item, dict) else None
                if content_list and isinstance(content_list, list):
                    for c in content_list:
                        if isinstance(c, dict):
                            # 'text' or 'content' fields may exist
                            if "text" in c:
                                parts.append(c["text"])
                            elif "content" in c and isinstance(c["content"], str):
                                parts.append(c["content"])
                # sometimes item has 'text' top-level
                if isinstance(item, dict) and "text" in item:
                    parts.append(item["text"])
            return "\n".join(parts).strip()
        except Exception:
            logger.exception("Failed to extract text from response object")
            return ""

    def _parse_response(self, response: Any) -> Dict:
        """
        Parse the AI response into a Python dict.
        Expects the model to return JSON (response_format=json_object).
        """
        text = self._extract_text_from_response(response)
        if not text:
            # If no text found, try retrieving raw string from response in other ways
            try:
                raw = getattr(response, "body", None) or getattr(response, "raw", None)
                if raw:
                    text = json.dumps(raw)
            except Exception:
                text = ""

        if not text:
            logger.error("No textual output extracted from model response.")
            raise RuntimeError("AI returned no output.")

        # Some models may wrap JSON in extra quotes or newlines — try to safely find JSON substring
        text_stripped = text.strip()
        # If text begins with a code fence or markdown, strip it (safety)
        if text_stripped.startswith("```"):
            # remove code fences
            parts = text_stripped.split("```")
            # choose the JSON-looking part if possible
            for p in parts:
                if p.strip().startswith("{"):
                    text_stripped = p.strip()
                    break

        # Now parse JSON
        try:
            data = json.loads(text_stripped)
            return data
        except json.JSONDecodeError as e:
            logger.warning("JSON decode failed, attempting to locate JSON substring...")
            # Try to locate first '{' and last '}' to extract substring
            start = text_stripped.find("{")
            end = text_stripped.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = text_stripped[start:end+1]
                try:
                    data = json.loads(candidate)
                    return data
                except json.JSONDecodeError:
                    logger.exception("Failed extracting JSON substring from model output")
            logger.error(f"Failed to parse model output as JSON. Raw output (first 1000 chars): {text_stripped[:1000]}")
            raise RuntimeError("Failed to parse AI response as JSON.")

    def _create_analysis_object(self, data: Dict) -> ContractAnalysis:
        """
        Convert parsed JSON into ContractAnalysis dataclasses.
        """
        red_flags = []
        for flag_data in data.get("red_flags", []):
            try:
                severity_raw = (flag_data.get("severity", "medium") or "medium").lower()
                severity = RiskLevel(severity_raw if severity_raw in RiskLevel._value2member_map_ else "medium")
                red_flags.append(
                    RedFlag(
                        clause_text=flag_data.get("clause_text", ""),
                        risk_type=flag_data.get("risk_type", ""),
                        explanation=flag_data.get("explanation", ""),
                        why_risky=flag_data.get("why_risky", ""),
                        suggested_alternative=flag_data.get("suggested_alternative", ""),
                        severity=severity,
                    )
                )
            except Exception:
                logger.exception("Skipping malformed red_flag entry")
                continue

        risk_data = data.get("risk_score", {})
        def parse_risk_field(key: str, default: str = "medium") -> RiskLevel:
            raw = (risk_data.get(key, default) or default).lower()
            return RiskLevel(raw if raw in RiskLevel._value2member_map_ else default)

        risk_score = RiskScore(
            financial_risk=parse_risk_field("financial_risk", "medium"),
            legal_exposure=parse_risk_field("legal_exposure", "medium"),
            fairness=parse_risk_field("fairness", "medium"),
            missing_clauses=parse_risk_field("missing_clauses", "medium"),
            overall_score=parse_risk_field("overall_score", "medium"),
        )

        analysis = ContractAnalysis(
            summary=data.get("summary", ""),
            key_terms=data.get("key_terms", {}),
            red_flags=red_flags,
            risk_score=risk_score,
            recommendations=data.get("recommendations", []),
            processing_time=0.0,
        )
        return analysis

    def to_dict(self, analysis: ContractAnalysis) -> Dict:
        """
        Convert ContractAnalysis to a JSON-serializable dict.
        """
        result = asdict(analysis)
        # convert RiskLevel enums to values
        result["risk_score"] = {k: getattr(v, "value", v) for k, v in result["risk_score"].items()}
        for flag in result.get("red_flags", []):
            if isinstance(flag.get("severity"), Enum):
                flag["severity"] = flag["severity"].value
        return result


# ------------------------------
# CLI / quick test harness
# ------------------------------
if __name__ == "__main__":
    # Example usage
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(" Error: OPENAI_API_KEY not found. Create a .env with OPENAI_API_KEY=sk-... or set the env var.")
        raise SystemExit(1)

    analyzer = ContractAnalyzer(api_key=api_key, model=os.getenv("OAI_MODEL", "gpt-4.1"))
    test_contract = """
    SOFTWARE LICENSE AGREEMENT

    This agreement is between TechCorp and Client.

    TERMS:
    1. Payment: $5,000 per month, due immediately. Late payments incur 10% penalty per day.
    2. Duration: 12 months, automatically renews unless cancelled 180 days in advance.
    3. Termination: TechCorp can terminate immediately. Client must give 6 months notice.
    4. Liability: Client is fully responsible for all damages, regardless of cause.
    5. Data: All client data becomes property of TechCorp.
    """

    print("Analyzing contract (this may take a few seconds)...")
    analysis = analyzer.analyze(test_contract)
    out = analyzer.to_dict(analysis)
    print(json.dumps(out, indent=2))