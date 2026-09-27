"""Live Clerk organization directory for project access administration."""

import httpx
from fastapi import HTTPException

from app.core.config import settings


def members(organization_id: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    try:
        with httpx.Client(timeout=5.0) as client:
            for offset in range(0, 500, 100):
                response = client.get(
                    f"https://api.clerk.com/v1/organizations/{organization_id}/memberships",
                    params={"limit": 100, "offset": offset},
                    headers={
                        "Authorization": f"Bearer {settings.clerk_secret_key.get_secret_value()}"
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("data"), list
                ):
                    raise ValueError("Invalid member response")
                for membership in payload["data"]:
                    user = membership.get("public_user_data") or {}
                    user_id = user.get("user_id")
                    if isinstance(user_id, str):
                        result.append(
                            {
                                "user_id": user_id,
                                "identifier": user.get("identifier") or user_id,
                                "organization_role": membership.get("role") or "",
                            }
                        )
                if offset + len(payload["data"]) >= payload.get("total_count", 0):
                    return result
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, "Organization members could not be loaded.") from None
    raise HTTPException(503, "Organization members could not be loaded.")
