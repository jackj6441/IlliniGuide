from time import perf_counter

from fastapi import FastAPI, Request

from app.api import chat, compare, health, metrics, recommend
from app.observability.metrics import observe_http_request


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

    @app.middleware("http")
    async def record_http_metrics(request: Request, call_next):
        started_at = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            observe_http_request(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_seconds=perf_counter() - started_at,
            )

    app.include_router(metrics.router)
    return app


app = create_app()
