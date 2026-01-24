"""GraphQL query resolvers for Feedback entity."""
import strawberry
from typing import List, Optional
from strawberry.types import Info

from .types import FeedbackType, FeedbackTypeEnum, FeedbackStatusEnum
from repositories import feedbacks_repo
from utils.graphql_auth import require_auth, require_role


@strawberry.type
class FeedbackQuery:
    @strawberry.field(description="Obtener todos los feedbacks (requiere rol admin)")
    async def feedbacks(self, info: Info, jwt: str) -> List[FeedbackType]:
        """Get all feedbacks. Requires admin role."""
        require_role(jwt, info, ["admin"])
        feedbacks = await feedbacks_repo.get_all()
        return [
            FeedbackType(
                id=f.id,
                userId=f.userId,
                type=FeedbackTypeEnum(f.type),
                description=f.description,
                rating=f.rating,
                status=FeedbackStatusEnum(f.status),
                createdAt=f.createdAt,
                updatedAt=f.updatedAt
            ) for f in feedbacks
        ]

    @strawberry.field(description="Obtener feedback por ID")
    async def feedback(self, info: Info, id: str, jwt: str) -> Optional[FeedbackType]:
        """Get feedback by ID. User can only see their own feedback unless admin."""
        user_id = require_auth(jwt, info)
        feedback = await feedbacks_repo.get_by_id(id)
        
        if not feedback:
            return None
        
        # Check authorization: user can only view their own feedback unless admin
        user_role = info.context.get("role")
        if feedback.userId != user_id and user_role != "admin":
            raise Exception("No autorizado para ver este feedback")
        
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

    @strawberry.field(description="Obtener mis feedbacks")
    async def my_feedbacks(self, info: Info, jwt: str) -> List[FeedbackType]:
        """Get feedbacks by current user."""
        user_id = require_auth(jwt, info)
        feedbacks = await feedbacks_repo.get_by_user(user_id)
        return [
            FeedbackType(
                id=f.id,
                userId=f.userId,
                type=FeedbackTypeEnum(f.type),
                description=f.description,
                rating=f.rating,
                status=FeedbackStatusEnum(f.status),
                createdAt=f.createdAt,
                updatedAt=f.updatedAt
            ) for f in feedbacks
        ]

    @strawberry.field(description="Obtener feedbacks por tipo (requiere rol admin)")
    async def feedbacks_by_type(
        self, 
        info: Info, 
        type: FeedbackTypeEnum, 
        jwt: str
    ) -> List[FeedbackType]:
        """Get feedbacks by type. Requires admin role."""
        require_role(jwt, info, ["admin"])
        feedbacks = await feedbacks_repo.get_by_type(type.value)
        return [
            FeedbackType(
                id=f.id,
                userId=f.userId,
                type=FeedbackTypeEnum(f.type),
                description=f.description,
                rating=f.rating,
                status=FeedbackStatusEnum(f.status),
                createdAt=f.createdAt,
                updatedAt=f.updatedAt
            ) for f in feedbacks
        ]

    @strawberry.field(description="Obtener feedbacks por estado (requiere rol admin)")
    async def feedbacks_by_status(
        self, 
        info: Info, 
        status: FeedbackStatusEnum, 
        jwt: str
    ) -> List[FeedbackType]:
        """Get feedbacks by status. Requires admin role."""
        require_role(jwt, info, ["admin"])
        feedbacks = await feedbacks_repo.get_by_status(status.value)
        return [
            FeedbackType(
                id=f.id,
                userId=f.userId,
                type=FeedbackTypeEnum(f.type),
                description=f.description,
                rating=f.rating,
                status=FeedbackStatusEnum(f.status),
                createdAt=f.createdAt,
                updatedAt=f.updatedAt
            ) for f in feedbacks
        ]
