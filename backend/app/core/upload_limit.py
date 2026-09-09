"""Bound the whole multipart body before Starlette can spool unlimited data."""

from fastapi import HTTPException
from starlette.responses import JSONResponse
from app.core.config import settings


class UploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        limit = settings.max_upload_bytes + 65536  # bounded multipart overhead
        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = limit + 1
        if declared > limit:
            return await JSONResponse(
                {"detail": "Request exceeds the configured upload size limit."},
                status_code=413,
            )(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(
                    413, "Request exceeds the configured upload size limit."
                )
            return message

        await self.app(scope, bounded_receive, send)
