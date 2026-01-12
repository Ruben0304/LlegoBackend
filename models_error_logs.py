"""Pydantic models for error logging system."""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal
from datetime import datetime
from enum import Enum


class ErrorSeverity(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


class ErrorSource(str, Enum):
    BACKEND = "backend"
    MOBILE_ANDROID = "mobile_android"
    MOBILE_IOS = "mobile_ios"
    WEB = "web"


class GeminiAnalysis(BaseModel):
    """Analysis response from Gemini AI."""
    resumen: str
    tipo_error: str
    archivo: Optional[str] = None
    linea: Optional[int] = None
    causa_probable: str
    soluciones: List[str]
    severidad: ErrorSeverity
    requiere_accion_inmediata: bool


class ErrorLog(BaseModel):
    """Error log model for MongoDB storage."""
    id: str = Field(alias="_id")
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    user_id: Optional[str] = None
    source: ErrorSource
    app_version: Optional[str] = None
    device_info: Optional[str] = None
    screen: Optional[str] = None
    action: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    gemini_analysis: Optional[GeminiAnalysis] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    created_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class MobileErrorReport(BaseModel):
    """Request schema for mobile error reports."""
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    source: Literal["mobile_android", "mobile_ios"]
    app_version: str
    device_info: Optional[str] = None
    screen: Optional[str] = None
    action: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None


class ErrorLogResponse(BaseModel):
    """Response schema for error log."""
    id: str
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    user_id: Optional[str] = None
    source: str
    app_version: Optional[str] = None
    device_info: Optional[str] = None
    screen: Optional[str] = None
    action: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    gemini_analysis: Optional[GeminiAnalysis] = None
    resolved: bool
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    created_at: datetime


class PaginatedErrorLogs(BaseModel):
    """Paginated response for error logs."""
    items: List[ErrorLogResponse]
    total_items: int
    total_pages: int
    page: int
    page_size: int


class ErrorStats(BaseModel):
    """Statistics for error logs."""
    total_errors: int
    resolved_errors: int
    pending_errors: int
    by_severity: Dict[str, int]
    by_source: Dict[str, int]
    by_type: Dict[str, int]
    critical_unresolved: int
    period_days: int
