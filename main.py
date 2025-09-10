# This is a sample Python script.

# Press Mayús+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import strawberry
from strawberry.fastapi import GraphQLRouter
from typing import List

from models import Store, Product, stores_repo, products_repo
from fastapi.responses import PlainTextResponse, Response


# FastAPI application
app = FastAPI(title="Llego Backend", version="0.1.0")

# CORS: allow all origins (use cautiously in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# GraphQL schema using Strawberry
@strawberry.type
class StoreType:
    id: int
    name: str
    etaMinutes: int
    logoUrl: str
    bannerUrl: str


@strawberry.type
class ProductType:
    id: int
    name: str
    shop: str
    weight: str
    price: str
    imageUrl: str
@strawberry.type
class Query:
    hello: str = strawberry.field(description="Saludo de ejemplo")

    @strawberry.field(description="Saluda por nombre")
    def greet(self, name: str = "mundo") -> str:
        return f"Hola, {name}!"

    @strawberry.field(description="Lista de tiendas")
    def stores(self) -> List[StoreType]:
        return [StoreType(**s.model_dump()) for s in stores_repo.get_stores()]

    @strawberry.field(description="Lista de productos")
    def products(self) -> List[ProductType]:
        return [ProductType(**p.model_dump()) for p in products_repo.get_products()]


schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema, graphiql=True)

# Mount GraphQL at /graphql
app.include_router(graphql_app, prefix="/graphql")


# Simple REST endpoint
@app.get("/")
def read_root():
    return {"status": "ok", "message": "Llego Backend con FastAPI y GraphQL listo"}


# GraphQL SDL schema endpoints
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


# REST endpoints using Pydantic models
@app.get("/stores", response_model=List[Store])
def list_stores():
    return stores_repo.get_stores()


@app.get("/products", response_model=List[Product])
def list_products():
    return products_repo.get_products()


if __name__ == "__main__":
    # Run the app with: python main.py
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

