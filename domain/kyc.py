"""Domain models for cash KYC verification."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from .py_object_id import PyObjectId


class KycVerdict(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"


class KycEvalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING_EVIDENCE = "pending_evidence"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    INSUFFICIENT_DATA = "insufficient_data"
    ERROR = "error"
    EXPIRED = "expired"


class CashCoverageStatus(str, Enum):
    ELIGIBLE_COVERED = "eligible_covered"
    ELIGIBLE_UNCOVERED = "eligible_uncovered"
    BLOCKED = "blocked"


class KycVerification(BaseModel):
    id: PyObjectId = Field(alias="_id")
    paymentAttemptId: PyObjectId
    orderId: PyObjectId
    customerId: PyObjectId
    merchantId: PyObjectId
    branchId: PyObjectId
    policyVersion: str
    minConfidence: float
    evidenceRefs: List[Dict[str, str]]
    evidenceHash: str
    requestId: str
    correlationId: str
    idempotencyKey: str
    provider: str = "gemini"
    verdict: Optional[str] = None
    confidenceScore: Optional[float] = None
    reasonCodes: List[str] = Field(default_factory=list)
    extractedSignals: Optional[Dict[str, Any]] = None
    modelVersion: Optional[str] = None
    evaluatedAt: Optional[datetime] = None
    status: str = KycEvalStatus.SUBMITTED.value
    retryCount: int = 0
    lastError: Optional[str] = None
    approvedAt: Optional[datetime] = None
    expiresAt: Optional[datetime] = None
    forceReverify: bool = False
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
        use_enum_values = True


class KycNotificationLog(BaseModel):
    id: PyObjectId = Field(alias="_id")
    kycVerificationId: PyObjectId
    merchantId: PyObjectId
    eventType: str
    channel: str
    status: str = "pending"
    attempts: int = 0
    lastError: Optional[str] = None
    sentAt: Optional[datetime] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}


class KycAuditEvent(BaseModel):
    id: PyObjectId = Field(alias="_id")
    entityType: str
    entityId: str
    eventType: str
    actorType: str
    actorId: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat(), ObjectId: str}
