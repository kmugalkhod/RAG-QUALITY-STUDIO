"""Change only the isolated widget browser fixture; never touch developer data."""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import app.models.index  # noqa: F401
import app.models.pipeline  # noqa: F401
import app.models.project  # noqa: F401
from app.core.config import settings
from app.models.deployment import AnswerDeployment, WidgetToken
from app.models.pipeline import PipelineVersion

config_file = Path(tempfile.gettempdir()) / f"rag-widget-browser-{os.getuid()}.json"
config = json.loads(config_file.read_text())
url = make_url(settings.database_url).set(database="rag_widget_browser_test")
engine = create_engine(url)

with Session(engine) as session:
    row = session.scalar(
        select(AnswerDeployment).where(AnswerDeployment.id == config["deployment_id"])
    )
    if row is None:
        raise RuntimeError("Fixture deployment missing")
    action = sys.argv[1]
    if action == "pause":
        row.state = "paused"
    elif action == "resume":
        row.state = "active"
    elif action == "disable":
        row.widget_enabled = False
    elif action == "enable":
        row.widget_enabled = True
    elif action == "position-right":
        row.widget_branding = {**row.widget_branding, "position": "right"}
    elif action == "fix-layout":
        version = session.scalar(
            select(PipelineVersion).where(
                PipelineVersion.pipeline_id == row.pipeline_id
            )
        )
        version.layout = {"positions": {}}
    elif action == "expire":
        session.query(WidgetToken).filter(
            WidgetToken.deployment_id == row.id, WidgetToken.revoked_at.is_(None)
        ).update(
            {WidgetToken.expires_at: datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
    else:
        raise RuntimeError("Unknown fixture action")
    session.commit()
