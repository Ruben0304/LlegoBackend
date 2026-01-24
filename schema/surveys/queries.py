"""GraphQL query resolvers for Survey entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import (
    SurveyType, 
    SurveyResponseType, 
    SurveyQuestionType, 
    QuestionTypeEnum,
    QuestionResponseType
)
from repositories import surveys_repo, survey_responses_repo
from utils.graphql_auth import require_auth, require_role


@strawberry.type
class SurveyQuery:
    @strawberry.field(description="Obtener todas las encuestas activas")
    async def active_surveys(self, info: Info, jwt: str) -> List[SurveyType]:
        """Get all active surveys. Requires authentication."""
        require_auth(jwt, info)
        surveys = await surveys_repo.get_active()
        return [
            SurveyType(
                id=s.id,
                title=s.title,
                description=s.description,
                questions=[
                    SurveyQuestionType(
                        questionId=q.questionId,
                        text=q.text,
                        type=QuestionTypeEnum(q.type),
                        options=q.options,
                        required=q.required
                    ) for q in s.questions
                ],
                isActive=s.isActive,
                createdAt=s.createdAt,
                updatedAt=s.updatedAt
            ) for s in surveys
        ]

    @strawberry.field(description="Obtener todas las encuestas (requiere rol admin)")
    async def all_surveys(self, info: Info, jwt: str) -> List[SurveyType]:
        """Get all surveys (including inactive). Requires admin role."""
        require_role(jwt, info, ["admin"])
        surveys = await surveys_repo.get_all()
        return [
            SurveyType(
                id=s.id,
                title=s.title,
                description=s.description,
                questions=[
                    SurveyQuestionType(
                        questionId=q.questionId,
                        text=q.text,
                        type=QuestionTypeEnum(q.type),
                        options=q.options,
                        required=q.required
                    ) for q in s.questions
                ],
                isActive=s.isActive,
                createdAt=s.createdAt,
                updatedAt=s.updatedAt
            ) for s in surveys
        ]

    @strawberry.field(description="Obtener encuesta por ID")
    async def survey(self, info: Info, id: str, jwt: str) -> Optional[SurveyType]:
        """Get survey by ID. Requires authentication."""
        require_auth(jwt, info)
        survey = await surveys_repo.get_by_id(id)
        
        if not survey:
            return None
        
        return SurveyType(
            id=survey.id,
            title=survey.title,
            description=survey.description,
            questions=[
                SurveyQuestionType(
                    questionId=q.questionId,
                    text=q.text,
                    type=QuestionTypeEnum(q.type),
                    options=q.options,
                    required=q.required
                ) for q in survey.questions
            ],
            isActive=survey.isActive,
            createdAt=survey.createdAt,
            updatedAt=survey.updatedAt
        )

    @strawberry.field(description="Obtener respuestas por encuesta (requiere rol admin)")
    async def survey_responses(
        self, 
        info: Info, 
        survey_id: str, 
        jwt: str
    ) -> List[SurveyResponseType]:
        """Get all responses for a survey. Requires admin role."""
        require_role(jwt, info, ["admin"])
        responses = await survey_responses_repo.get_by_survey(survey_id)
        return [
            SurveyResponseType(
                id=r.id,
                surveyId=r.surveyId,
                userId=r.userId,
                responses=[
                    QuestionResponseType(
                        questionId=qr.questionId,
                        answer=qr.answer
                    ) for qr in r.responses
                ],
                createdAt=r.createdAt
            ) for r in responses
        ]

    @strawberry.field(description="Obtener mis respuestas a encuestas")
    async def my_survey_responses(self, info: Info, jwt: str) -> List[SurveyResponseType]:
        """Get current user's survey responses."""
        user_id = require_auth(jwt, info)
        responses = await survey_responses_repo.get_by_user(user_id)
        return [
            SurveyResponseType(
                id=r.id,
                surveyId=r.surveyId,
                userId=r.userId,
                responses=[
                    QuestionResponseType(
                        questionId=qr.questionId,
                        answer=qr.answer
                    ) for qr in r.responses
                ],
                createdAt=r.createdAt
            ) for r in responses
        ]

    @strawberry.field(description="Verificar si el usuario ya respondió una encuesta")
    async def has_responded_to_survey(
        self, 
        info: Info, 
        survey_id: str, 
        jwt: str
    ) -> bool:
        """Check if current user has already responded to a survey."""
        user_id = require_auth(jwt, info)
        response = await survey_responses_repo.get_by_survey_and_user(survey_id, user_id)
        return response is not None
