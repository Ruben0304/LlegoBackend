"""GraphQL mutations for Feedback entity."""
import strawberry
from typing import Optional
from datetime import datetime
from strawberry.types import Info

from .types import FeedbackType, FeedbackTypeEnum, FeedbackStatusEnum
from .inputs import CreateFeedbackInput, UpdateFeedbackStatusInput
from repositories import feedbacks_repo
from utils.graphql_auth import require_auth, require_role


@strawberry.type
class FeedbackMutation:
    @strawberry.mutation(description="Crear un nuevo feedback")
    async def create_feedback(
        self,
        info: Info,
        input: CreateFeedbackInput,
        jwt: str
    ) -> FeedbackType:
        """Create a new feedback. Requires authentication."""
        user_id = require_auth(jwt, info)

        # Validate rating range
        if input.rating < 1 or input.rating > 5:
            raise Exception("El rating debe estar entre 1 y 5")

        # Create feedback data
        feedback_data = {
            "userId": user_id,
            "type": input.type.value,
            "description": input.description,
            "rating": input.rating,
            "status": "PENDING",
            "createdAt": datetime.utcnow(),
            "updatedAt": None
        }

        # Create in database
        feedback = await feedbacks_repo.create(feedback_data)

        return FeedbackType(
            id=feedback.id,
            userId=feedback.userId,
            type=FeedbackTypeEnum(feedback.type),
            description=feedback.description,
            rating=feedback.rating,
            status=FeedbackStatusEnum(feedback.status),
            createdAt=feedback.createdAt,
            updatedAt=feedback.updatedAt
        )

    @strawberry.mutation(description="Actualizar estado de feedback (requiere rol admin)")
    async def update_feedback_status(
        self,
        info: Info,
        feedback_id: str,
        input: UpdateFeedbackStatusInput,
        jwt: str
    ) -> FeedbackType:
        """Update feedback status. Requires admin role."""
        require_role(jwt, info, ["admin"])

        # Check if feedback exists
        feedback = await feedbacks_repo.get_by_id(feedback_id)
        if not feedback:
            raise Exception("Feedback no encontrado")

        # Update status
        updates = {"status": input.status.value}
        updated_feedback = await feedbacks_repo.update(feedback_id, updates)

        if not updated_feedback:
            raise Exception("Error al actualizar el feedback")

        return FeedbackType(
            id=updated_feedback.id,
            userId=updated_feedback.userId,
            type=FeedbackTypeEnum(updated_feedback.type),
            description=updated_feedback.description,
            rating=updated_feedback.rating,
            status=FeedbackStatusEnum(updated_feedback.status),
            createdAt=updated_feedback.createdAt,
            updatedAt=updated_feedback.updatedAt
        )

    @strawberry.mutation(description="Eliminar un feedback")
    async def delete_feedback(
        self,
        info: Info,
        feedback_id: str,
        jwt: str
    ) -> bool:
        """Delete a feedback. User can only delete their own feedback unless admin."""
        user_id = require_auth(jwt, info)
        user_role = info.context.get("role")

        # Get feedback to check ownership
        feedback = await feedbacks_repo.get_by_id(feedback_id)
        if not feedback:
            raise Exception("Feedback no encontrado")

        # Check authorization: user can only delete their own feedback unless admin
        if feedback.userId != user_id and user_role != "admin":
            raise Exception("No autorizado para eliminar este feedback")

        # Delete feedback
        success = await feedbacks_repo.delete(feedback_id)
        if not success:
            raise Exception("Error al eliminar el feedback")

        return True
