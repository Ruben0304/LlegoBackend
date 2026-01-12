"""Error analysis service using Gemini AI."""
import re
import json
import asyncio
from typing import Optional, Dict, Any

from clients import get_gemini_client
from core.config import settings
from models_error_logs import GeminiAnalysis


# Patterns for sanitizing sensitive data
SENSITIVE_PATTERNS = [
    (r'password["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'password=***REDACTED***'),
    (r'token["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'token=***REDACTED***'),
    (r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'api_key=***REDACTED***'),
    (r'secret["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'secret=***REDACTED***'),
    (r'bearer\s+[a-zA-Z0-9\-_.]+', 'Bearer ***REDACTED***'),
    (r'mongodb(\+srv)?://[^@]+@', 'mongodb://***REDACTED***@'),
    (r'redis://[^@]+@', 'redis://***REDACTED***@'),
    (r'postgres(ql)?://[^@]+@', 'postgresql://***REDACTED***@'),
    (r'mysql://[^@]+@', 'mysql://***REDACTED***@'),
    (r'aws[_-]?secret[_-]?access[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'aws_secret_access_key=***REDACTED***'),
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '***EMAIL***'),
]


def sanitize_sensitive_data(text: str) -> str:
    """Remove sensitive data from text before sending to Gemini."""
    if not text:
        return text
    
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    
    return sanitized


ANALYSIS_PROMPT = """Analiza el siguiente error de una aplicación Python/FastAPI y responde ÚNICAMENTE con un JSON válido (sin markdown, sin explicaciones adicionales).

Error Type: {error_type}
Error Message: {error_message}
Stack Trace:
{stack_trace}

Endpoint: {endpoint}
HTTP Method: {http_method}
Source: {source}

Responde con este formato JSON exacto:
{{
  "resumen": "string - resumen breve del error en español",
  "tipo_error": "string - categoría del error (ej: ValidationError, DatabaseError, AuthError, NetworkError, etc)",
  "archivo": "string o null - archivo donde ocurrió si se puede determinar del stack trace",
  "linea": "int o null - línea aproximada si se puede determinar",
  "causa_probable": "string - causa más probable del error en español",
  "soluciones": ["array de strings con posibles soluciones en español"],
  "severidad": "baja | media | alta | critica",
  "requiere_accion_inmediata": true/false
}}

Criterios de severidad:
- critica: Errores que afectan la disponibilidad del sistema o seguridad
- alta: Errores que afectan funcionalidad importante
- media: Errores que afectan funcionalidad secundaria
- baja: Errores menores o warnings"""


class ErrorAnalysisService:
    """Service for analyzing errors using Gemini AI."""

    def __init__(self):
        self.model_name = settings.gemini_model

    def _build_prompt(
        self,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str],
        endpoint: Optional[str],
        http_method: Optional[str],
        source: str
    ) -> str:
        """Build the analysis prompt with sanitized data."""
        return ANALYSIS_PROMPT.format(
            error_type=sanitize_sensitive_data(error_type),
            error_message=sanitize_sensitive_data(error_message),
            stack_trace=sanitize_sensitive_data(stack_trace or "No disponible"),
            endpoint=endpoint or "No disponible",
            http_method=http_method or "No disponible",
            source=source
        )

    async def analyze_error(
        self,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
        source: str = "backend"
    ) -> Optional[GeminiAnalysis]:
        """Analyze an error using Gemini AI."""
        try:
            client = get_gemini_client()
            prompt = self._build_prompt(
                error_type, error_message, stack_trace,
                endpoint, http_method, source
            )

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model_name,
                contents=prompt
            )

            if not response.text:
                return None

            # Parse JSON response
            text = response.text.strip()
            # Remove markdown code blocks if present
            if text.startswith("```"):
                text = re.sub(r'^```(?:json)?\n?', '', text)
                text = re.sub(r'\n?```$', '', text)

            data = json.loads(text)
            return GeminiAnalysis(**data)

        except Exception as e:
            print(f"Error analyzing with Gemini: {e}")
            return None

    async def analyze_and_update(self, error_id: str, error_data: Dict[str, Any]) -> None:
        """Analyze error and update the database record (background task)."""
        # Import here to avoid circular imports
        from repositories.error_log_repository import error_log_repo
        from services.push_notification_service import notify_critical_error
        
        print(f"🔍 Starting analysis for error {error_id}")
        
        try:
            analysis = await self.analyze_error(
                error_type=error_data.get("error_type", "Unknown"),
                error_message=error_data.get("error_message", ""),
                stack_trace=error_data.get("stack_trace"),
                endpoint=error_data.get("endpoint"),
                http_method=error_data.get("http_method"),
                source=error_data.get("source", "backend")
            )

            if analysis:
                print(f"✅ Analysis complete - severidad: {analysis.severidad}")
                await error_log_repo.update_analysis(error_id, analysis.model_dump())
                
                # Send push notification for ALL errors
                print(f"🚨 Sending push notification for error...")
                await notify_critical_error(
                    error_id=error_id,
                    error_type=error_data.get("error_type", "Unknown"),
                    error_message=error_data.get("error_message", ""),
                    severity=analysis.severidad
                )
            else:
                print(f"⚠️ No analysis returned from Gemini")

        except Exception as e:
            print(f"❌ Error in background analysis for {error_id}: {e}")


# Singleton instance
error_analysis_service = ErrorAnalysisService()
