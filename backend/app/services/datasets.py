import csv
import hashlib
import io
from fastapi import HTTPException
from sqlalchemy import select, func
from app.core.config import settings
from app.models.experiment import Dataset, DatasetVersion
from app.services.documents import project, paginate

EXAMPLE = "question,reference_answer\nWhat fruit does the orchard grow?,The orchard grows apples.\nWho founded the orchard?,\n"


def preview(data: bytes):
    if len(data) > settings.dataset_max_bytes:
        raise HTTPException(413, "Dataset exceeds the configured file limit.")
    errors, rows = [], []
    try:
        source = data.decode("utf-8-sig")
        if "\x00" in source:
            raise ValueError()
        reader = csv.reader(io.StringIO(source, newline=""), strict=True)
        headers = next(reader, [])
        if headers not in (
            ["question"],
            ["question", "reference_answer"],
            ["reference_answer", "question"],
        ):
            return {
                "rows": [],
                "errors": [
                    {
                        "row": 1,
                        "message": "Use question (required) and reference_answer (optional) headers, without duplicates or extra columns.",
                    }
                ],
                "content_hash": hashlib.sha256(data).hexdigest(),
            }
        for ordinal, cells in enumerate(reader, 2):
            if ordinal - 1 > settings.dataset_max_rows:
                errors.append(
                    {
                        "row": ordinal,
                        "message": f"Maximum {settings.dataset_max_rows} questions per dataset.",
                    }
                )
                break
            if len(cells) != len(headers):
                errors.append(
                    {"row": ordinal, "message": "Column count does not match headers."}
                )
                continue
            row = {key: value.strip() for key, value in zip(headers, cells)}
            if not row["question"] or len(row["question"]) > 4000:
                errors.append(
                    {
                        "row": ordinal,
                        "message": "Question must contain 1–4,000 characters.",
                    }
                )
            if len(row.get("reference_answer", "")) > 12000:
                errors.append(
                    {
                        "row": ordinal,
                        "message": "Reference answer exceeds 12,000 characters.",
                    }
                )
            rows.append(
                {
                    "question": row["question"],
                    "reference_answer": row.get("reference_answer") or None,
                }
            )
        if not rows and not errors:
            errors.append({"row": 2, "message": "Include at least one question."})
    except (UnicodeError, ValueError, csv.Error):
        errors.append(
            {
                "row": len(rows) + 2,
                "message": "Upload valid UTF-8 CSV with properly quoted fields.",
            }
        )
    return {
        "rows": rows,
        "errors": errors,
        "content_hash": hashlib.sha256(data).hexdigest(),
    }


def import_version(session, project_id, name, data, expected_hash, dataset_id=None):
    project(session, project_id)
    parsed = preview(data)
    if parsed["errors"]:
        raise HTTPException(422, parsed["errors"])
    if parsed["content_hash"] != expected_hash:
        raise HTTPException(
            409, "File changed after preview. Preview it again before importing."
        )
    name = name.strip()
    if not 1 <= len(name) <= 120:
        raise HTTPException(422, "Dataset name must contain 1–120 characters.")
    if dataset_id:
        dataset = session.scalar(
            select(Dataset)
            .where(Dataset.id == dataset_id, Dataset.project_id == project_id)
            .with_for_update()
        )
        if dataset is None:
            raise HTTPException(404, "Dataset not found in this project.")
    else:
        dataset = Dataset(project_id=project_id, name=name)
        session.add(dataset)
        session.flush()
    number = (
        session.scalar(
            select(func.max(DatasetVersion.version)).where(
                DatasetVersion.dataset_id == dataset.id
            )
        )
        or 0
    ) + 1
    version = DatasetVersion(
        dataset_id=dataset.id,
        project_id=project_id,
        name=name,
        version=number,
        content_hash=parsed["content_hash"],
        rows=parsed["rows"],
    )
    session.add(version)
    session.commit()
    return version


def get_version(session, project_id, version_id):
    row = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.id == version_id, DatasetVersion.project_id == project_id
        )
    )
    if row is None:
        raise HTTPException(404, "Dataset version not found in this project.")
    return row


def listing(session, project_id, limit, offset):
    project(session, project_id)
    return paginate(
        session,
        select(DatasetVersion)
        .where(DatasetVersion.project_id == project_id)
        .order_by(DatasetVersion.created_at.desc(), DatasetVersion.id),
        limit,
        offset,
    )
