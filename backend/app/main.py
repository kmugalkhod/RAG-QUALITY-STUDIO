from app.api.experiments import router as experiment_router
from app.api.connections import router as connection_router
from app.api.pipelines import router as pipeline_router
from app.api.queries import router as query_router
from app.api.indexes import router as index_router
from app.api.ingestion import router as ingestion_router
from app.api.deployments import router as deployment_router
from app.api.deployed_answers import router as deployed_answer_router
from app.api.widget import router as widget_router
from app.api.deployment_metrics import router as deployment_metrics_router
from app.api.schedules import router as schedule_router
from app.api.provider_credentials import router as provider_credential_router
from app.providers.embeddings import EmbeddingError
from app.api.documents import router as document_router
from app.core.upload_limit import UploadLimitMiddleware
from fastapi import FastAPI, HTTPException, Request, Response
from uuid import uuid4
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.api.routes import router
from app.core.config import settings
from app.core.auth import validate_security_configuration
from app.core.artifact_crypto import (
    ArtifactConfigurationError,
    ArtifactUnavailableError,
)
from app.core.connection_secrets import SecretDecryptionError

validate_security_configuration()
app = FastAPI(title="RAG Quality Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "If-Match", "Idempotency-Key"],
)
app.include_router(router)
app.include_router(connection_router)
app.include_router(experiment_router)
app.include_router(document_router)
app.include_router(index_router)
app.include_router(ingestion_router)
app.include_router(schedule_router)
app.include_router(query_router)
app.include_router(pipeline_router)
app.include_router(deployment_router)
app.include_router(deployed_answer_router)
app.include_router(widget_router)
app.include_router(deployment_metrics_router)
app.include_router(provider_credential_router)
app.add_middleware(UploadLimitMiddleware)


def _deployment_path(request: Request) -> bool:
    path = request.url.path
    return path.startswith("/v1/answer-deployments/") or (
        path.startswith("/api/projects/") and "/answer-deployments" in path
    )


def _deployment_error(
    request: Request, status: int, code: str, message: str, details=None
):
    headers = {"Cache-Control": "no-store"}
    if status in {429, 503}:
        headers["Retry-After"] = "2"
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": str(uuid4()),
                "details": details or [],
            }
        },
    )


@app.middleware("http")
async def deployment_browser_boundary(request: Request, call_next):
    path = request.url.path
    deployed_path = path.startswith("/v1/answer-deployments/")
    widget_browser = (
        deployed_path and "/widget/" in path and not path.endswith("/widget/config")
    )
    widget_public = deployed_path and path.endswith("/widget/config")
    origin = request.headers.get("origin")
    if widget_browser:
        allowed = origin == settings.widget_frame_origin and settings.widget_enabled
        if request.method == "OPTIONS":
            if not allowed or request.headers.get(
                "access-control-request-method"
            ) not in {"GET", "POST"}:
                return _deployment_error(
                    request, 403, "origin_not_allowed", "Origin not allowed."
                )
            requested = {
                part.strip().lower()
                for part in request.headers.get(
                    "access-control-request-headers", ""
                ).split(",")
                if part.strip()
            }
            if not requested <= {"authorization", "content-type", "idempotency-key"}:
                return _deployment_error(
                    request, 403, "origin_not_allowed", "Origin not allowed."
                )
            response = Response(status_code=204)
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, Idempotency-Key"
            )
            response.headers["Access-Control-Max-Age"] = "300"
            response.headers["Vary"] = "Origin"
            return response
        if not allowed:
            return _deployment_error(
                request, 403, "origin_not_allowed", "Origin not allowed."
            )
    elif deployed_path and not widget_public and origin:
        return _deployment_error(
            request,
            403,
            "browser_origin_disabled",
            "Browser-origin requests are disabled.",
        )
    response = await call_next(request)
    if widget_public and origin == settings.widget_frame_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    if widget_browser:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Referrer-Policy"] = "no-referrer"
    if _deployment_path(request) and not widget_public:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if _deployment_path(request):
        if isinstance(exc.detail, dict):
            return _deployment_error(
                request,
                exc.status_code,
                exc.detail["code"],
                exc.detail["message"],
                exc.detail.get("details"),
            )
        detail = str(exc.detail)
        code = (
            detail
            if detail.isidentifier() and detail.islower()
            else {
                401: "unauthorized",
                402: "budget_exhausted",
                403: "forbidden",
                404: "not_found",
                409: "conflict",
                410: "gone",
                412: "stale_revision",
                422: "invalid_request",
                428: "precondition_required",
                429: "rate_limited",
                503: "unavailable",
            }.get(exc.status_code, "request_failed")
        )
        message = (
            detail if code != detail else code.replace("_", " ").capitalize() + "."
        )
        return _deployment_error(request, exc.status_code, code, message)
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    if _deployment_path(request):
        return _deployment_error(
            request, 503, "database_unavailable", "Database unavailable."
        )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable. Please try again shortly."},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not echo submitted data back in errors.
    errors = [
        {"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()
    ]
    if _deployment_path(request):
        return _deployment_error(
            request, 422, "invalid_request", "Invalid request.", errors
        )
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(EmbeddingError)
async def embedding_error(request: Request, exc: EmbeddingError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(SecretDecryptionError)
async def connection_decryption_error(request: Request, exc: SecretDecryptionError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Stored connection credentials are unavailable."},
    )


@app.exception_handler(ArtifactConfigurationError)
@app.exception_handler(ArtifactUnavailableError)
async def artifact_encryption_error(request: Request, exc: RuntimeError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Encrypted artifact storage is unavailable."},
    )
