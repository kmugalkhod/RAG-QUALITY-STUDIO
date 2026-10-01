"""Worker-to-worker hand-off; the dispatcher remains the recovery path."""

import logging

from sqlalchemy import update
from sqlalchemy.orm import Session


def hand_off(db_engine, model, job_id, send, countdown=None):
    """Deliver the next step now; if the broker is down, let the dispatcher resend."""
    try:
        send(job_id, countdown=countdown)
    except Exception:
        logging.warning(
            "Worker hand-off unavailable; dispatcher will resend %s.", job_id
        )
        with Session(db_engine) as session:
            session.execute(
                update(model)
                .where(model.id == job_id, model.status == "queued")
                .values(dispatched_at=None)
            )
            session.commit()
