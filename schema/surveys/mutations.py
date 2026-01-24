"""GraphQL mutations for Survey entity."""
import strawberry
from typing import Optional
from datetime import datetime
from strawberry.types import Info

from .types import (
    SurveyType, 
    SurveyResponseType, 
    SurveyQuestionType, 
    QuestionTypeEnum,
    QuestionResponseType
)
from .inputs import (
    CreateSurveyInput, 
    UpdateSurveyInput, 
    SubmitSurveyResponseInput,
    SurveyQuestionInput
)
from repositories import surveys_repo, survey_responses_repo
from utils.graphql_auth import require_auth, require_role


@strawberry.type
class SurveyMutation:
    @strawberry.mutation(description="Crear una nueva encuesta (requiere rol admin)")
    async def create_survey(
        self,
        info: Info,
        input: CreateSurveyInput,
        jwt: str
    ) -> SurveyType:
        """Create a new survey. Requires admin role."""
        require_role(jwt, info, ["admin"])

        # Validate that questions with MULTIPLE_CHOICE have options
        for q in input.questions:
            if q.type == QuestionTypeEnum.MULTIPLE_CHOICE and not q.options:
                raise Exception(f"La pregunta '{q.text}' de tipo MULTIPLE_CHOICE requiere opciones")

        # Create survey data
        survey_data = {
            "title": input.title,
            "description": input.description,
            "questions": [
                {
                    "questionId": q.questionId,
                    "text": q.text,
                    "type": q.type.value,
                    "options": q.options,
                    "required": q.required
                } for q in input.questions
            ],
            "isActive": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": None
        }

        # Create in database
        survey = await surveys_repo.create(survey_data)

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

    @strawberry.mutation(description="Actualizar una encuesta (requiere rol admin)")
    async def update_survey(
        self,
        info: Info,
        survey_id: str,
        input: UpdateSurveyInput,
        jwt: str
    ) -> SurveyType:
        """Update a survey. Requires admin role."""
        require_role(jwt, info, ["admin"])

        # Check if survey exists
        survey = await surveys_repo.get_by_id(survey_id)
        if not survey:
            raise Exception("Encuesta no encontrada")

        # Build updates dict
        updates = {}
        if input.title is not None:
            updates["title"] = input.title
        if input.description is not None:
            updates["description"] = input.description
        if input.isActive is not None:
            updates["isActive"] = input.isActive
        if input.questions is not None:
            # Validate questions
            for q in input.questions:
                if q.type == QuestionTypeEnum.MULTIPLE_CHOICE and not q.options:
                    raise Exception(f"La pregunta '{q.text}' de tipo MULTIPLE_CHOICE requiere opciones")
            
            updates["questions"] = [
                {
                    "questionId": q.questionId,
                    "text": q.text,
                    "type": q.type.value,
                    "options": q.options,
                    "required": q.required
                } for q in input.questions
            ]

        if not updates:
            raise Exception("No hay campos para actualizar")

        # Update survey
        updated_survey = await surveys_repo.update(survey_id, updates)

        if not updated_survey:
            raise Exception("Error al actualizar la encuesta")

        return SurveyType(
            id=updated_survey.id,
            title=updated_survey.title,
            description=updated_survey.description,
            questions=[
                SurveyQuestionType(
                    questionId=q.questionId,
                    text=q.text,
                    type=QuestionTypeEnum(q.type),
                    options=q.options,
                    required=q.required
                ) for q in updated_survey.questions
            ],
            isActive=updated_survey.isActive,
            createdAt=updated_survey.createdAt,
            updatedAt=updated_survey.updatedAt
        )

    @strawberry.mutation(description="Desactivar una encuesta (requiere rol admin)")
    async def deactivate_survey(
        self,
        info: Info,
        survey_id: str,
        jwt: str
    ) -> SurveyType:
        """Deactivate a survey. Requires admin role."""
        require_role(jwt, info, ["admin"])

        # Check if survey exists
        survey = await surveys_repo.get_by_id(survey_id)
        if not survey:
            raise Exception("Encuesta no encontrada")

        # Deactivate survey
        deactivated_survey = await surveys_repo.deactivate(survey_id)

        if not deactivated_survey:
            raise Exception("Error al desactivar la encuesta")

        return SurveyType(
            id=deactivated_survey.id,
            title=deactivated_survey.title,
            description=deactivated_survey.description,
            questions=[
                SurveyQuestionType(
                    questionId=q.questionId,
                    text=q.text,
                    type=QuestionTypeEnum(q.type),
                    options=q.options,
                    required=q.required
                ) for q in deactivated_survey.questions
            ],
            isActive=deactivated_survey.isActive,
            createdAt=deactivated_survey.createdAt,
            updatedAt=deactivated_survey.updatedAt
        )

    @strawberry.mutation(description="Enviar respuesta a una encuesta")
    async def submit_survey_response(
        self,
        info: Info,
        input: SubmitSurveyResponseInput,
        jwt: str
    ) -> SurveyResponseType:
        """Submit a response to a survey. Requires authentication."""
        user_id = require_auth(jwt, info)

        # Check if survey exists and is active
        survey = await surveys_repo.get_by_id(input.surveyId)
        if not survey:
            raise Exception("Encuesta no encontrada")
        if not survey.isActive:
            raise Exception("La encuesta no está activa")

        # Check if user has already responded
        existing_response = await survey_responses_repo.get_by_survey_and_user(
            input.surveyId, 
            user_id
        )
        if existing_response:
            raise Exception("Ya has respondido esta encuesta")

        # Validate responses match questions
        question_ids = {q.questionId for q in survey.questions}
        response_ids = {r.questionId for r in input.responses}
        
        # Check for missing required questions
        required_question_ids = {q.questionId for q in survey.questions if q.required}
        missing_required = required_question_ids - response_ids
        if missing_required:
            raise Exception(f"Faltan respuestas para preguntas requeridas: {missing_required}")

        # Check for invalid question IDs
        invalid_ids = response_ids - question_ids
        if invalid_ids:
            raise Exception(f"IDs de pregunta inválidos: {invalid_ids}")

        # Validate MULTIPLE_CHOICE answers are valid options
        for response in input.responses:
            question = next((q for q in survey.questions if q.questionId == response.questionId), None)
            if question and question.type == "MULTIPLE_CHOICE":
                if question.options and response.answer not in question.options:
                    raise Exception(
                        f"Respuesta inválida para pregunta '{question.text}': "
                        f"'{response.answer}' no es una opción válida"
                    )

        # Create response data
        response_data = {
            "surveyId": input.surveyId,
            "userId": user_id,
            "responses": [
                {
                    "questionId": r.questionId,
                    "answer": r.answer
                } for r in input.responses
            ],
            "createdAt": datetime.utcnow()
        }

        # Create in database
        survey_response = await survey_responses_repo.create(response_data)

        return SurveyResponseType(
            id=survey_response.id,
            surveyId=survey_response.surveyId,
            userId=survey_response.userId,
            responses=[
                QuestionResponseType(
                    questionId=qr.questionId,
                    answer=qr.answer
                ) for qr in survey_response.responses
            ],
            createdAt=survey_response.createdAt
        )

    @strawberry.mutation(description="Eliminar una encuesta (requiere rol admin)")
    async def delete_survey(
        self,
        info: Info,
        survey_id: str,
        jwt: str
    ) -> bool:
        """Delete a survey. Requires admin role."""
        require_role(jwt, info, ["admin"])

        # Check if survey exists
        survey = await surveys_repo.get_by_id(survey_id)
        if not survey:
            raise Exception("Encuesta no encontrada")

        # Delete survey
        success = await surveys_repo.delete(survey_id)
        if not success:
            raise Exception("Error al eliminar la encuesta")

        return True
