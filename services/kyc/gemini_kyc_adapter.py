"""Gemini adapter for cash KYC evaluation."""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel

from clients.gemini_client import get_gemini_client
from core.config import settings
from services.error_analysis_service import sanitize_sensitive_data

logger = logging.getLogger(__name__)


class GeminiKycAdapter:
    """Calls Gemini API and normalizes response to internal KYC contract."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self) -> None:
        self.model = settings.gemini_model
        self.max_retries = settings.cash_kyc_max_auto_retries

    def _build_prompt(self, request_payload: Dict[str, Any]) -> str:
        return (
            "Evalua riesgo KYC para pago en efectivo. "
            "Responde SOLO JSON con: verdict, confidence_score, reason_codes, extracted_signals, model_version."
            f"\nData: {json.dumps(request_payload, ensure_ascii=True)}"
        )

    @staticmethod
    def _get_client() -> genai.Client:
        try:
            return get_gemini_client()
        except Exception:
            return genai.Client(api_key=settings.gemini_api_key)

    async def evaluate(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate KYC with retries for transient errors."""
        if not settings.gemini_api_key:
            return {
                "verdict": "error",
                "confidence_score": 0.0,
                "reason_codes": ["GEMINI_API_KEY_MISSING"],
                "extracted_signals": {},
                "provider": "gemini",
                "model_version": self.model,
                "policy_version": request_payload.get("policy_version"),
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "request_id": request_payload.get("request_id"),
                "correlation_id": request_payload.get("correlation_id"),
                "error": "Gemini API key not configured",
            }

        timeout = httpx.Timeout(connect=0.5, read=2.0, write=2.0, pool=2.5)
        url = f"{self.BASE_URL}/models/{self.model}:generateContent?key={settings.gemini_api_key}"
        body = {
            "contents": [
                {
                    "parts": [{"text": self._build_prompt(request_payload)}],
                }
            ]
        }
        headers = {"Content-Type": "application/json"}
        correlation_id = request_payload.get("correlation_id")

        attempt = 0
        while True:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, headers=headers, json=body)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError(
                        f"Transient Gemini error {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return self._normalize_response(
                    response.json(),
                    request_payload=request_payload,
                )
            except (
                httpx.TimeoutException,
                httpx.NetworkError,
                httpx.HTTPStatusError,
            ) as exc:
                if attempt > self.max_retries:
                    logger.warning(
                        "kyc_gemini_failed correlation_id=%s attempts=%s error=%s",
                        correlation_id,
                        attempt - 1,
                        sanitize_sensitive_data(str(exc)),
                    )
                    break
                base_delay = [1, 3, 9, 27][min(attempt - 1, 3)]
                await asyncio.sleep(base_delay + random.uniform(0, 0.5))
            except Exception as exc:  # non-transient mapping or payload errors
                logger.exception(
                    "kyc_gemini_unexpected correlation_id=%s error=%s",
                    correlation_id,
                    sanitize_sensitive_data(str(exc)),
                )
                break

        return {
            "verdict": "error",
            "confidence_score": 0.0,
            "reason_codes": ["PROVIDER_ERROR"],
            "extracted_signals": {},
            "provider": "gemini",
            "model_version": self.model,
            "policy_version": request_payload.get("policy_version"),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "request_id": request_payload.get("request_id"),
            "correlation_id": request_payload.get("correlation_id"),
            "error": "Provider unavailable",
        }

    def _normalize_response(
        self,
        payload: Dict[str, Any],
        *,
        request_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Normalize Gemini response to internal contract."""
        text = ""
        candidates = payload.get("candidates") or []
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and isinstance(parts[0], dict):
                text = parts[0].get("text", "")

        parsed = {}
        if text:
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = {}

        verdict = (parsed.get("verdict") or "error").lower()
        confidence = parsed.get("confidence_score")
        try:
            confidence_value = float(confidence) if confidence is not None else 0.0
        except Exception:
            confidence_value = 0.0

        return {
            "verdict": verdict,
            "confidence_score": confidence_value,
            "reason_codes": parsed.get("reason_codes") or [],
            "extracted_signals": parsed.get("extracted_signals") or {},
            "provider": "gemini",
            "model_version": parsed.get("model_version") or self.model,
            "policy_version": request_payload.get("policy_version"),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "request_id": request_payload.get("request_id"),
            "correlation_id": request_payload.get("correlation_id"),
        }

    async def evaluate_with_images(
        self,
        *,
        request_payload: Dict[str, Any],
        selfie_with_id_bytes: bytes,
        selfie_with_id_mime_type: str,
        identity_document_front_bytes: bytes,
        identity_document_front_mime_type: str,
    ) -> Dict[str, Any]:
        """Evaluate KYC with real image bytes using Gemini multimodal API."""
        if not settings.gemini_api_key:
            return {
                "verdict": "error",
                "confidence_score": 0.0,
                "reason_codes": ["GEMINI_API_KEY_MISSING"],
                "extracted_signals": {},
                "provider": "gemini",
                "model_version": self.model,
                "policy_version": request_payload.get("policy_version"),
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "request_id": request_payload.get("request_id"),
                "correlation_id": request_payload.get("correlation_id"),
                "error": "Gemini API key not configured",
            }

        class GeminiKycVisionResponse(BaseModel):
            verdict: str
            confidence_score: float
            reason_codes: list[str] = []
            extracted_signals: dict[str, Any] = {}
            model_version: str

        system_instruction = (
            "Eres un verificador KYC de identidad. "
            "Recibirás dos imágenes: "
            "(1) selfie de una persona sosteniendo su documento, "
            "(2) foto frontal del documento de identidad. "
            "Evalúa coherencia de identidad, presencia real del documento en la selfie, "
            "legibilidad del documento y suficiencia de evidencia. "
            "Responde estricto JSON con campos: verdict, confidence_score, reason_codes, extracted_signals, model_version. "
            "verdict permitido: valid, invalid, needs_review, insufficient_data, error."
        )

        try:
            client = self._get_client()
            response = await client.aio.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    genai_types.Part.from_text(
                        text=json.dumps(request_payload, ensure_ascii=True)
                    ),
                    genai_types.Part.from_bytes(
                        data=selfie_with_id_bytes,
                        mime_type=selfie_with_id_mime_type,
                    ),
                    genai_types.Part.from_bytes(
                        data=identity_document_front_bytes,
                        mime_type=identity_document_front_mime_type,
                    ),
                ],
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=GeminiKycVisionResponse,
                    temperature=0.1,
                ),
            )
            parsed = GeminiKycVisionResponse.model_validate_json(response.text)
            return {
                "verdict": (parsed.verdict or "error").lower(),
                "confidence_score": float(parsed.confidence_score or 0.0),
                "reason_codes": parsed.reason_codes or [],
                "extracted_signals": parsed.extracted_signals or {},
                "provider": "gemini",
                "model_version": parsed.model_version or self.model,
                "policy_version": request_payload.get("policy_version"),
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "request_id": request_payload.get("request_id"),
                "correlation_id": request_payload.get("correlation_id"),
            }
        except Exception as exc:
            logger.warning(
                "kyc_gemini_image_failed correlation_id=%s error=%s",
                request_payload.get("correlation_id"),
                sanitize_sensitive_data(str(exc)),
            )
            return {
                "verdict": "error",
                "confidence_score": 0.0,
                "reason_codes": ["PROVIDER_ERROR"],
                "extracted_signals": {},
                "provider": "gemini",
                "model_version": self.model,
                "policy_version": request_payload.get("policy_version"),
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
                "request_id": request_payload.get("request_id"),
                "correlation_id": request_payload.get("correlation_id"),
                "error": "Provider unavailable",
            }


gemini_kyc_adapter = GeminiKycAdapter()
