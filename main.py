from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from strawberry.fastapi import GraphQLRouter
import uvicorn

from clients import lifespan
from schema import schema
from api import router


# FastAPI application with lifespan for all clients
app = FastAPI(title="Llego Backend", version="0.1.0", lifespan=lifespan)

# CORS: allow all origins (use cautiously in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount GraphQL router
graphql_app = GraphQLRouter(schema, graphiql=True)
app.include_router(graphql_app, prefix="/graphql")

# Mount REST API router
app.include_router(router)


@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "ok", "message": "Llego Backend con FastAPI y GraphQL listo"}


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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

