from fastapi import APIRouter

from app.api.routes import Database
from app.core.auth import CurrentPrincipal
from app.schemas.provider_credential import ProviderKeyRead, ProviderKeySave
from app.services import provider_credentials

# The key itself is write-only: no route returns it, only a redacted hint.
router = APIRouter(prefix="/api/organizations/current/provider-credentials")


@router.get("", response_model=ProviderKeyRead)
def read_provider_key(session: Database, principal: CurrentPrincipal):
    return provider_credentials.read(session, principal)


@router.put("/openrouter", response_model=ProviderKeyRead)
def save_provider_key(
    data: ProviderKeySave, session: Database, principal: CurrentPrincipal
):
    return provider_credentials.save(session, principal, data.api_key)


@router.post("/openrouter/test", response_model=ProviderKeyRead)
def test_provider_key(session: Database, principal: CurrentPrincipal):
    return provider_credentials.test(session, principal)


@router.delete("/openrouter", response_model=ProviderKeyRead)
def delete_provider_key(session: Database, principal: CurrentPrincipal):
    return provider_credentials.delete(session, principal)
