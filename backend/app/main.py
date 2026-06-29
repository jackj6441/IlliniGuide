from fastapi import FastAPI

from app.api import chat, compare, health, recommend


def create_app() -> FastAPI:
    app = FastAPI(
        title="IlliniGuide Serve API",
        version="0.1.0",
        description="Mocked FastAPI skeleton for the IlliniGuide Serve advising platform.",
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(compare.router)
    app.include_router(recommend.router)
    return app


app = create_app()
