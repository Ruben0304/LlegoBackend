"""Gemini adapter for cash KYC evaluation."""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from clients.gemini_client import get_gemini_client
from core.config import settings
from services.error_analysis_service import sanitize_sensitive_data

logger = logging.getLogger(__name__)


class GeminiKycResponse(BaseModel):
    verdict: str
    confidence_score: float
    reason_codes: list[str] = []
    extracted_signals: dict[str, Any] = {}
    model_version: str


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
    def _build_provider_error(exc: Exception) -> str:
        if isinstance(exc, genai_errors.APIError):
            status = getattr(exc, "status", None)
            message = getattr(exc, "message", None) or str(exc)
            if status:
                return f"Gemini API error {status}: {message}"
            return f"Gemini API error: {message}"
        return str(exc)

    @staticmethod
    def _build_provider_error_code(provider_error: str) -> str:
        normalized = (provider_error or "").lower()
        if "high demand" in normalized or "experiencing high demand" in normalized:
            return "GEMINI_MODEL_OVERLOADED"
        if "timed out" in normalized or "timeout" in normalized:
            return "GEMINI_TIMEOUT"
        if "api key not configured" in normalized or "api key not valid" in normalized:
            return "GEMINI_AUTH_ERROR"
        if "validation failed" in normalized:
            return "GEMINI_RESPONSE_VALIDATION_ERROR"
        return "GEMINI_PROVIDER_ERROR"

    def _normalize_structured_response(
        self,
        parsed: GeminiKycResponse,
        *,
        request_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
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

    @staticmethod
    def _get_client() -> genai.Client:
        try:
            return get_gemini_client()
        except Exception:
            return genai.Client(api_key=settings.gemini_api_key)

    async def evaluate(self, request_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate KYC with retries for transient errors."""
        if not settings.gemini_api_key:
            logger.warning(
                "kyc_gemini_missing_api_key correlation_id=%s request_id=%s",
                request_payload.get("correlation_id"),
                request_payload.get("request_id"),
            )
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
                "error_code": "GEMINI_AUTH_ERROR",
            }

        correlation_id = request_payload.get("correlation_id")
        client = self._get_client()

        attempt = 0
        last_error = "Provider unavailable"
        while True:
            attempt += 1
            try:
                response = await client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=[genai_types.Part.from_text(text=self._build_prompt(request_payload))],
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=GeminiKycResponse,
                        temperature=0.1,
                    ),
                )
                parsed = GeminiKycResponse.model_validate_json(response.text)
                normalized = self._normalize_structured_response(
                    parsed,
                    request_payload=request_payload,
                )
                logger.info(
                    "kyc_gemini_evaluated correlation_id=%s request_id=%s verdict=%s confidence=%s model=%s",
                    correlation_id,
                    request_payload.get("request_id"),
                    normalized.get("verdict"),
                    normalized.get("confidence_score"),
                    normalized.get("model_version"),
                )
                return normalized
            except (genai_errors.ServerError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = self._build_provider_error(exc)
                if attempt > self.max_retries:
                    logger.warning(
                        "kyc_gemini_failed correlation_id=%s attempts=%s error=%s",
                        correlation_id,
                        attempt - 1,
                        sanitize_sensitive_data(last_error),
                    )
                    break
                base_delay = [1, 3, 9, 27][min(attempt - 1, 3)]
                await asyncio.sleep(base_delay + random.uniform(0, 0.5))
            except (genai_errors.ClientError, genai_errors.APIError) as exc:
                last_error = self._build_provider_error(exc)
                logger.warning(
                    "kyc_gemini_client_error correlation_id=%s request_id=%s error=%s",
                    correlation_id,
                    request_payload.get("request_id"),
                    sanitize_sensitive_data(last_error),
                )
                break
            except ValidationError as exc:
                last_error = f"Gemini response validation failed: {exc}"
                logger.warning(
                    "kyc_gemini_validation_failed correlation_id=%s request_id=%s error=%s",
                    correlation_id,
                    request_payload.get("request_id"),
                    sanitize_sensitive_data(last_error),
                )
                break
            except Exception as exc:  # non-transient mapping or payload errors
                last_error = self._build_provider_error(exc)
                logger.exception(
                    "kyc_gemini_unexpected correlation_id=%s error=%s",
                    correlation_id,
                    sanitize_sensitive_data(last_error),
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
            "error": last_error,
            "error_code": self._build_provider_error_code(last_error),
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
            logger.warning(
                "kyc_gemini_missing_api_key_with_images correlation_id=%s request_id=%s",
                request_payload.get("correlation_id"),
                request_payload.get("request_id"),
            )
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
                "error_code": "GEMINI_AUTH_ERROR",
            }

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
                    response_schema=GeminiKycResponse,
                    temperature=0.1,
                ),
            )
            parsed = GeminiKycResponse.model_validate_json(response.text)
            normalized = self._normalize_structured_response(
                parsed,
                request_payload=request_payload,
            )
            logger.info(
                "kyc_gemini_image_evaluated correlation_id=%s request_id=%s verdict=%s confidence=%s model=%s",
                request_payload.get("correlation_id"),
                request_payload.get("request_id"),
                normalized.get("verdict"),
                normalized.get("confidence_score"),
                normalized.get("model_version"),
            )
            return normalized
        except (genai_errors.ClientError, genai_errors.ServerError, genai_errors.APIError) as exc:
            provider_error = self._build_provider_error(exc)
            logger.warning(
                "kyc_gemini_image_api_failed correlation_id=%s error=%s",
                request_payload.get("correlation_id"),
                sanitize_sensitive_data(provider_error),
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
                "error": provider_error,
                "error_code": self._build_provider_error_code(provider_error),
            }
        except ValidationError as exc:
            provider_error = f"Gemini response validation failed: {exc}"
            logger.warning(
                "kyc_gemini_image_validation_failed correlation_id=%s error=%s",
                request_payload.get("correlation_id"),
                sanitize_sensitive_data(provider_error),
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
                "error": provider_error,
                "error_code": self._build_provider_error_code(provider_error),
            }
        except Exception as exc:
            provider_error = self._build_provider_error(exc)
            logger.warning(
                "kyc_gemini_image_failed correlation_id=%s error=%s",
                request_payload.get("correlation_id"),
                sanitize_sensitive_data(provider_error),
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
                "error": provider_error,
                "error_code": self._build_provider_error_code(provider_error),
            }


gemini_kyc_adapter = GeminiKycAdapter()
