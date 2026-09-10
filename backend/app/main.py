from app.api.queries import router as query_router
from app.api.indexes import router as index_router
from app.providers.embeddings import EmbeddingError
from app.api.documents import router as document_router
from app.core.upload_limit import UploadLimitMiddleware
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.api.routes import router
from app.core.config import settings

app = FastAPI(title="RAG Quality Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(router)
app.include_router(document_router)
app.include_router(index_router)
app.include_router(query_router)
app.add_middleware(UploadLimitMiddleware)


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
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
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(EmbeddingError)
async def embedding_error(request: Request, exc: EmbeddingError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})
