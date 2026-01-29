from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from strawberry.fastapi import GraphQLRouter
from slowapi.errors import RateLimitExceeded
import uvicorn
import logging
import asyncio

from clients import lifespan
from schema import schema
from api import router
from core.config import settings
from utils.rate_limit import limiter, rate_limit_exceeded_handler, get_redis_status
from utils.dataloaders import create_dataloaders
from utils.exception_handler import global_exception_handler, http_exception_handler
from services.access_expiration_worker import expire_old_accesses

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
    openapi_url="/openapi.json" if is_development else None
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

async def get_graphql_context(request: Request, response: Response) -> dict:
    """Provide a mutable context for resolvers with DataLoaders."""
    return {
        "request": request,
        "response": response,
        "user_id": None,
        "user_role": None,
        **create_dataloaders()  # Add DataLoaders to context
    }


# Mount GraphQL router
# GraphiQL is disabled in production for security
graphql_app = GraphQLRouter(
    schema,
    graphiql=is_development,  # Only enable in development
    context_getter=get_graphql_context
)
app.include_router(graphql_app, prefix="/graphql")

# Mount REST API router
app.include_router(router)


# Background task for expiring old access
async def run_expiration_worker():
    """Background task that runs every 15 minutes to expire old access."""
    while True:
        try:
            logger.info("Running access expiration worker...")
            await expire_old_accesses()
            logger.info("Access expiration worker completed successfully")
        except Exception as e:
            logger.error(f"Error in access expiration worker: {e}", exc_info=True)
        
        # Wait 15 minutes before next run
        await asyncio.sleep(900)


@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup."""
    logger.info("Starting access expiration worker...")
    asyncio.create_task(run_expiration_worker())


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
