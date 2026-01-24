"""GraphQL type definitions for Survey entity."""
import strawberry
from datetime import datetime
from typing import Optional, List
from enum import Enum


@strawberry.enum
class QuestionTypeEnum(Enum):
    """Types of survey questions."""
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TEXT = "TEXT"


@strawberry.type
class SurveyQuestionType:
    """Survey question embedded in a survey."""
    questionId: str
    text: str
    type: QuestionTypeEnum
    options: Optional[List[str]] = None
    required: bool


@strawberry.type
class SurveyType:
    """Survey with embedded questions."""
    id: str
    title: str
    description: Optional[str]
    questions: List[SurveyQuestionType]
    isActive: bool
    createdAt: datetime
    updatedAt: Optional[datetime]


@strawberry.type
class QuestionResponseType:
    """User's answer to a specific question."""
    questionId: str
    answer: str


@strawberry.type
class SurveyResponseType:
    """User's complete response to a survey."""
    id: str
    surveyId: str
    userId: str
    responses: List[QuestionResponseType]
    createdAt: datetime
