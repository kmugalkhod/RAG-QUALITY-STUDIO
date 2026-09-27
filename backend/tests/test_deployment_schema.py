"""Isolated PostgreSQL checks for the additive release schema."""

from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.deployment import AnswerDeployment, AnswerDeploymentRelease
from app.models.index import IndexVersion, KnowledgeSet
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.project import Project


def _objects(session):
    owner = uuid4()
    project = Project(name="Deployment schema", organization_id="org_schema_a")
    foreign = Project(name="Foreign schema", organization_id="org_schema_b")
    session.add_all([project, foreign])
    session.flush()
    pipeline = Pipeline(project_id=project.id, name="Saved", kind="answer")
    knowledge = KnowledgeSet(project_id=project.id, name="Index")
    session.add_all([pipeline, knowledge])
    session.flush()
    index = IndexVersion(
        project_id=project.id,
        knowledge_set_id=knowledge.id,
        version=1,
        dimensions=3,
        embedding_config={"provider": "test"},
        status="succeeded",
        chunk_count=1,
        embedded_count=1,
        attempts=0,
        failures=0,
    )
    session.add(index)
    session.flush()
    execution = {"schema_version": 1, "nodes": [], "edges": []}
    version = PipelineVersion(
        project_id=project.id,
        pipeline_id=pipeline.id,
        version=1,
        name="Saved",
        execution=execution,
        layout={},
    )
    session.add(version)
    session.flush()
    deployment = AnswerDeployment(
        organization_id=project.organization_id,
        project_id=project.id,
        pipeline_id=pipeline.id,
        name="Endpoint",
        created_by=owner,
    )
    session.add(deployment)
    session.flush()
    release = AnswerDeploymentRelease(
        deployment_id=deployment.id,
        organization_id=project.organization_id,
        project_id=project.id,
        pipeline_id=pipeline.id,
        pipeline_version_id=version.id,
        index_id=index.id,
        release_number=1,
        execution=execution,
        execution_sha256=sha256(b"execution").hexdigest(),
        embedding_config=index.embedding_config,
        embedding_sha256=sha256(b"embedding").hexdigest(),
        schema_version=1,
        created_by=owner,
        note="",
    )
    session.add(release)
    session.flush()
    return project, foreign, pipeline, version, index, deployment, release


def test_release_schema_preserves_ownership_and_immutability(database):
    engine, _ = database
    with engine.connect() as connection:
        outer = connection.begin()
        try:
            with Session(bind=connection) as session:
                project, foreign, pipeline, version, index, deployment, release = (
                    _objects(session)
                )
                with pytest.raises(DBAPIError):
                    with session.begin_nested():
                        session.execute(
                            text(
                                "UPDATE answer_deployment_releases SET note = 'changed' WHERE id = :id"
                            ),
                            {"id": release.id},
                        )
                with pytest.raises(DBAPIError):
                    with session.begin_nested():
                        session.execute(
                            text(
                                "DELETE FROM answer_deployment_releases WHERE id = :id"
                            ),
                            {"id": release.id},
                        )
                with pytest.raises(DBAPIError):
                    with session.begin_nested():
                        session.execute(
                            text("""
                                INSERT INTO answer_deployments
                                (id, organization_id, project_id, pipeline_id, name, state, revision, created_by)
                                VALUES (:id, :org, :project, :pipeline, 'Foreign', 'paused', 1, :actor)
                            """),
                            {
                                "id": uuid4(),
                                "org": foreign.organization_id,
                                "project": project.id,
                                "pipeline": pipeline.id,
                                "actor": uuid4(),
                            },
                        )
                assert (
                    session.scalar(
                        text(
                            "SELECT count(*) FROM answer_deployment_releases WHERE id = :id"
                        ),
                        {"id": release.id},
                    )
                    == 1
                )
        finally:
            outer.rollback()
