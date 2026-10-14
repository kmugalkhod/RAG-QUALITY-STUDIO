from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.routes import Database
from app.core.auth import require_project_access
from app.schemas.setting_recommendations import (
    SettingRecommendationRead,
    SettingRecommendationRequest,
)
from app.services import setting_recommendations

router = APIRouter(
    prefix="/api/projects/{project_id}",
    dependencies=[Depends(require_project_access)],
)


@router.post(
    "/setting-recommendations",
    response_model=SettingRecommendationRead,
    status_code=202,
)
def start(project_id: UUID, data: SettingRecommendationRequest, session: Database):
    return setting_recommendations.start(session, project_id, data)


@router.get(
    "/setting-recommendations/{recommendation_id}",
    response_model=SettingRecommendationRead,
)
def read(project_id: UUID, recommendation_id: UUID, session: Database):
    return setting_recommendations.read(session, project_id, recommendation_id)


@router.post(
    "/setting-recommendations/{recommendation_id}/cancel",
    response_model=SettingRecommendationRead,
)
def cancel(project_id: UUID, recommendation_id: UUID, session: Database):
    return setting_recommendations.cancel(session, project_id, recommendation_id)
