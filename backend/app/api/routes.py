from typing import Annotated
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text, select
from sqlalchemy.dialects.postgresql import insert
from uuid import UUID
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.schemas.project import (
    ProjectCreate,
    ProjectPage,
    ProjectRead,
    ProjectMembershipGrant,
)
from app.services import projects, organizations
from app.core.auth import CurrentPrincipal, require_project_access, _clerk_membership
from app.models.project import Project
from app.models.security import ProjectMembership, UserIdentity

router = APIRouter(prefix="/api")
Database = Annotated[Session, Depends(get_session)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(session: Database) -> dict[str, str]:
    session.execute(
        text(
            "SELECT id, name, description, organization_id, created_at FROM projects LIMIT 0"
        )
    )
    session.execute(text("SELECT storage_name, content_hash FROM documents LIMIT 0"))
    session.execute(text("SELECT status, execution_token FROM processing_runs LIMIT 0"))
    session.execute(text("SELECT run_id, ordinal FROM chunks LIMIT 0"))
    session.execute(
        text(
            "SELECT knowledge_set_id, embedding_config, embedded_count FROM index_versions LIMIT 0"
        )
    )
    session.execute(text("SELECT current_ready_index_id FROM knowledge_sets LIMIT 0"))
    session.execute(
        text("SELECT stage, progress, snapshot FROM ingestion_runs LIMIT 0")
    )
    session.execute(
        text("SELECT cadence, next_run_at, status FROM ingestion_schedules LIMIT 0")
    )
    session.execute(
        text("SELECT processing_run_id, status FROM ingestion_run_items LIMIT 0")
    )
    session.execute(
        text(
            "SELECT execution, status, protected_content, protected_schema "
            "FROM source_previews LIMIT 0"
        )
    )
    session.execute(text("SELECT reason, status FROM source_preview_items LIMIT 0"))
    session.execute(
        text("SELECT stage, ordinal FROM source_preview_representations LIMIT 0")
    )
    session.execute(text("SELECT identity_hash FROM source_items LIMIT 0"))
    session.execute(
        text("SELECT secret_schema_version, status FROM source_connections LIMIT 0")
    )
    session.execute(text("SELECT event_type FROM source_connection_events LIMIT 0"))
    session.execute(text("SELECT external_subject FROM user_identities LIMIT 0"))
    session.execute(text("SELECT role FROM project_memberships LIMIT 0"))
    session.execute(text("SELECT outcome FROM sensitive_access_events LIMIT 0"))
    session.execute(text("SELECT extracted_hash FROM source_revisions LIMIT 0"))
    session.execute(text("SELECT outcome, status FROM website_run_items LIMIT 0"))
    session.execute(
        text("SELECT status, source_config_hash FROM source_snapshots LIMIT 0")
    )
    session.execute(
        text(
            "SELECT snapshot_id, source_revision_id FROM source_snapshot_members LIMIT 0"
        )
    )
    session.execute(
        text(
            "SELECT index_id, source_revision_id, source_node_id "
            "FROM index_source_revisions LIMIT 0"
        )
    )
    session.execute(text("SELECT vector_dims(embedding) FROM index_chunks LIMIT 0"))
    session.execute(
        text("SELECT pipeline_version_id, snapshot FROM query_runs LIMIT 0")
    )
    session.execute(text("SELECT project_id, name, kind FROM pipelines LIMIT 0"))
    session.execute(text("SELECT execution, layout FROM pipeline_versions LIMIT 0"))
    session.execute(text("SELECT rows FROM dataset_versions LIMIT 0"))
    session.execute(text("SELECT snapshot, progress FROM experiments LIMIT 0"))
    session.execute(text("SELECT metrics, query_run_id FROM experiment_items LIMIT 0"))
    return {"status": "ready"}


@router.get("/projects", response_model=ProjectPage)
def list_projects(
    session: Database,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return projects.list_projects(session, limit, offset, principal)


@router.post("/projects", response_model=ProjectRead, status_code=201)
def create_project(data: ProjectCreate, session: Database, principal: CurrentPrincipal):
    return projects.create_project(session, data, principal)


@router.get("/organizations/current/members")
def list_current_organization_members(principal: CurrentPrincipal):
    if principal.auth_mode != "clerk" or not principal.organization_id:
        raise HTTPException(404, "Organization not found.")
    return {"items": organizations.members(principal.organization_id)}


@router.post("/projects/claim-unowned")
def claim_unowned_projects(session: Database, principal: CurrentPrincipal):
    if principal.auth_mode != "clerk" or principal.organization_role != "org:admin":
        raise HTTPException(403, "Organization admin access is required.")
    unowned = session.scalars(
        select(Project).where(
            Project.organization_id == principal.organization_id,
            ~select(ProjectMembership.project_id)
            .where(ProjectMembership.project_id == Project.id)
            .exists(),
        )
    ).all()
    claimed = 0
    for project in unowned:
        result = session.execute(
            insert(ProjectMembership)
            .values(project_id=project.id, user_id=principal.user_id, role="owner")
            .on_conflict_do_nothing(
                index_elements=[ProjectMembership.project_id, ProjectMembership.user_id]
            )
        )
        claimed += result.rowcount
    session.commit()
    return {"claimed": claimed}


@router.post(
    "/projects/{project_id}/memberships", dependencies=[Depends(require_project_access)]
)
def grant_project_membership(
    project_id: UUID,
    data: ProjectMembershipGrant,
    session: Database,
    principal: CurrentPrincipal,
):
    role = session.scalar(
        select(ProjectMembership.role).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == principal.user_id,
        )
    )
    if role not in {"owner", "admin"} or (
        role == "admin" and data.role in {"owner", "admin"}
    ):
        raise HTTPException(403, "This project role cannot grant the requested access.")
    project = session.get(Project, project_id)
    if principal.auth_mode == "clerk":
        if project.organization_id != principal.organization_id:
            raise HTTPException(404, "Project not found.")
        if not _clerk_membership(data.user_id, principal.organization_id):
            raise HTTPException(422, "The user is not a current organization member.")
    identity = session.scalar(
        select(UserIdentity).where(UserIdentity.external_subject == data.user_id)
    )
    if identity is None:
        identity = UserIdentity(external_subject=data.user_id)
        session.add(identity)
        session.flush()
    session.execute(
        insert(ProjectMembership)
        .values(project_id=project_id, user_id=identity.id, role=data.role)
        .on_conflict_do_update(
            index_elements=[ProjectMembership.project_id, ProjectMembership.user_id],
            set_={"role": data.role},
        )
    )
    session.commit()
    return {"user_id": data.user_id, "role": data.role}


@router.get(
    "/projects/{project_id}/memberships", dependencies=[Depends(require_project_access)]
)
def list_project_memberships(project_id: UUID, session: Database):
    rows = session.execute(
        select(UserIdentity.external_subject, ProjectMembership.role)
        .join(ProjectMembership, ProjectMembership.user_id == UserIdentity.id)
        .where(ProjectMembership.project_id == project_id)
    ).all()
    return {"items": [{"user_id": subject, "role": role} for subject, role in rows]}
