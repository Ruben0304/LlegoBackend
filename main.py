import logging
from typing import Optional, Union

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from slowapi.errors import RateLimitExceeded
from starlette.websockets import WebSocket
from strawberry.fastapi import BaseContext, GraphQLRouter

from api import router
from clients import lifespan
from core.config import settings
from schema import schema
from utils.dataloaders import create_dataloaders
from utils.exception_handler import global_exception_handler, http_exception_handler
from utils.rate_limit import get_redis_status, limiter, rate_limit_exceeded_handler

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# FastAPI application with lifespan for all clients
# Disable docs in production for security
is_development = settings.environment == "development"
app = FastAPI(
    title="Llego Backend",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if is_development else None,
    redoc_url="/redoc" if is_development else None,
    openapi_url="/openapi.json" if is_development else None,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Add global exception handlers for error logging
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# CORS configuration
# Mobile apps (iOS/Android) don't need CORS - they make native requests
# Only web origins need to be whitelisted
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every HTTP request."""
    logger.info(f"📨 Incoming request: {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"✅ Request completed: {request.method} {request.url.path} - Status: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"❌ Request failed: {request.method} {request.url.path} - Error: {e}", exc_info=True)
        raise


class CustomContext(BaseContext):
    """Custom GraphQL context with DataLoaders and auth info.

    Supports both HTTP (Request/Response) and WebSocket connections.
    """

    def __init__(
        self,
        request: Optional[Request] = None,
        response: Optional[Response] = None,
        websocket: Optional[WebSocket] = None,
    ):
        super().__init__()
        self.request = request
        self.response = response
        self.websocket = websocket
        self.user_id: Optional[str] = None
        self.user_role: Optional[str] = None
        # Add DataLoaders as attributes
        for key, value in create_dataloaders().items():
            setattr(self, key, value)

    def get(self, key: str, default=None):
        """Provide dict-like get access for backward compatibility."""
        return getattr(self, key, default)


async def get_graphql_context(request=None, response=None, websocket=None) -> CustomContext:
    """Provide a custom context for resolvers with DataLoaders.

    Supports both HTTP (request/response) and WebSocket connections.
    Strawberry will inject the appropriate parameters based on connection type.
    """
    # Determine if request is actually a WebSocket
    if isinstance(request, WebSocket):
        websocket = request
        request = None

    return CustomContext(
        request=request,
        response=response,
        websocket=websocket
    )


# Mount GraphQL router
# GraphiQL is disabled in production for security
graphql_app = GraphQLRouter(
    schema,
    graphql_ide="graphiql" if is_development else None,
    context_getter=get_graphql_context,
)
app.include_router(graphql_app, prefix="/graphql")

# Mount REST API router
app.include_router(router)


@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Llego Backend con FastAPI y GraphQL listo"}


@app.get("/health/redis")
def health_redis():
    """Redis connection status (for debugging rate limiting)."""
    return get_redis_status()


@app.get("/graphql/schema", response_class=PlainTextResponse)
def graphql_schema_sdl() -> str:
    """Returns the GraphQL schema in SDL format (plain text)."""
    return schema.as_str()


@app.get("/graphql/schema.graphql")
def graphql_schema_download():
    """Forces download of the GraphQL schema as a .graphql file."""
    sdl = schema.as_str()
    return Response(
        content=sdl,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="schema.graphql"'},
    )


if __name__ == "__main__":
    # Run the app with: python main.py
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
