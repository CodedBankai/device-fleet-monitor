"""Application entry point."""
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.routes import router

app = FastAPI(
    title="Device Fleet Monitor",
    description="Tracks heartbeats from a fleet of devices and reports ONLINE/OFFLINE status.",
    version="1.0.0",
)
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    # Body that is not valid JSON at all -> 400. Anything else (missing or
    # wrongly typed fields) keeps FastAPI's standard 422 response.
    if any(err.get("type") == "json_invalid" for err in exc.errors()):
        return JSONResponse(
            status_code=400,
            content={"detail": "Malformed JSON in request body"},
        )
    return await request_validation_exception_handler(request, exc)