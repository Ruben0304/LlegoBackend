"""GraphQL input types for Survey mutations."""
import strawberry
from typing import Optional, List
from .types import QuestionTypeEnum


@strawberry.input
class SurveyQuestionInput:
    """Input for creating a survey question."""
    questionId: str = strawberry.field(description="Unique ID for this question (e.g., UUID)")
    text: str
    type: QuestionTypeEnum
    options: Optional[List[str]] = None
    required: bool = True


@strawberry.input
class CreateSurveyInput:
    """Input for creating a survey."""
    title: str
    description: Optional[str] = None
    questions: List[SurveyQuestionInput]


@strawberry.input
class UpdateSurveyInput:
    """Input for updating a survey."""
    title: Optional[str] = None
    description: Optional[str] = None
    questions: Optional[List[SurveyQuestionInput]] = None
    isActive: Optional[bool] = None


@strawberry.input
class QuestionResponseInput:
    """Input for a single question response."""
    questionId: str
    answer: str


@strawberry.input
class SubmitSurveyResponseInput:
    """Input for submitting a survey response."""
    surveyId: str
    responses: List[QuestionResponseInput]
