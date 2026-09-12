from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.project import Project
from app.models.index import KnowledgeSet
from app.schemas.project import ProjectCreate, ProjectPage


def create_project(session: Session, data: ProjectCreate) -> Project:
    project = Project(**data.model_dump())
    session.add(project)
    session.flush()
    session.add(KnowledgeSet(project_id=project.id, name="Uploaded documents"))
    session.commit()
    session.refresh(project)
    return project


def list_projects(session: Session, limit: int, offset: int) -> ProjectPage:
    # A single repeatable-read transaction gives count and rows the same snapshot.
    total = session.scalar(select(func.count()).select_from(Project))
    items = session.scalars(
        select(Project)
        .order_by(Project.created_at.desc(), Project.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ProjectPage(items=items, total=total, limit=limit, offset=offset)
