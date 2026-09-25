from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.project import Project
from app.models.index import KnowledgeSet
from app.models.security import ProjectMembership
from app.core.auth import Principal
from app.schemas.project import ProjectCreate, ProjectPage


def create_project(
    session: Session, data: ProjectCreate, principal: Principal
) -> Project:
    project = Project(**data.model_dump())
    session.add(project)
    session.flush()
    session.add(KnowledgeSet(project_id=project.id, name="Uploaded documents"))
    if principal.auth_mode == "oidc":
        session.add(
            ProjectMembership(
                project_id=project.id, user_id=principal.user_id, role="owner"
            )
        )
    session.commit()
    session.refresh(project)
    return project


def list_projects(
    session: Session, limit: int, offset: int, principal: Principal
) -> ProjectPage:
    # A single repeatable-read transaction gives count and rows the same snapshot.
    query = select(Project)
    if principal.auth_mode == "oidc":
        query = query.join(
            ProjectMembership,
            ProjectMembership.project_id == Project.id,
        ).where(ProjectMembership.user_id == principal.user_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    items = session.scalars(
        query.order_by(Project.created_at.desc(), Project.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ProjectPage(items=items, total=total, limit=limit, offset=offset)
