from datetime import timedelta
from io import BytesIO
from uuid import UUID, uuid4
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models.document import Chunk, Document, ProcessingRun
from app.models.project import Project
from app.pipelines.parsing import ProcessingError, pages, validate_text, windows
from app.workers.dispatcher import dispatch_once
from app.workers.processing import now, process


def pdf_bytes(texts):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        if text:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): writer._add_object(font)}
                    )
                }
            )
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 20 250 Td ({text}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    "value,size,overlap,expected",
    [
        ("abcdefghij", 4, 1, [(0, 4, "abcd"), (3, 7, "defg"), (6, 10, "ghij")]),
        ("abcde", 4, 0, [(0, 4, "abcd"), (4, 5, "e")]),
        ("abcd", 4, 3, [(0, 4, "abcd")]),
        ("é😀\r\nx", 3, 1, [(0, 3, "é😀\r"), (2, 5, "\r\nx")]),
        (" ", 4, 0, []),
    ],
)
def test_windows(value, size, overlap, expected):
    assert list(windows(value, size, overlap)) == expected


@pytest.mark.parametrize("value", [b"", b" \n", b"\xff", b"a\x00b"])
def test_invalid_text(value):
    with pytest.raises(ProcessingError):
        validate_text(value)


def test_pdf_pages_and_blank_scanned_error(tmp_path):
    path = tmp_path / "source.pdf"
    path.write_bytes(pdf_bytes(["First page", "Second page"]))
    result = list(pages(path, "application/pdf"))
    assert [(r[0], r[1]) for r in result] == [(1, "First page"), (2, "Second page")]
    path.write_bytes(pdf_bytes([""]))
    with pytest.raises(ProcessingError, match="OCR"):
        list(pages(path, "application/pdf"))


@pytest.fixture
def documents_api(database, tmp_path, monkeypatch):
    engine, _ = database
    monkeypatch.setattr(settings, "storage_path", tmp_path)

    def sessions():
        with Session(
            engine.execution_options(isolation_level="READ COMMITTED")
        ) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        p = client.post("/api/projects", json={"name": "Document test"}).json()["id"]
        q = client.post("/api/projects", json={"name": "Other project"}).json()["id"]
        yield client, engine, p, q
    app.dependency_overrides.clear()
    with Session(engine) as session:
        ids = select(Document.id).where(Document.project_id.in_([UUID(p), UUID(q)]))
        runs = select(ProcessingRun.id).where(ProcessingRun.document_id.in_(ids))
        session.execute(delete(Chunk).where(Chunk.run_id.in_(runs)))
        session.execute(delete(ProcessingRun).where(ProcessingRun.document_id.in_(ids)))
        session.execute(delete(Document).where(Document.id.in_(ids)))
        session.execute(delete(Project).where(Project.id.in_([UUID(p), UUID(q)])))
        session.commit()


def upload(client, p, content=b"abcdefghij", name="source.txt"):
    response = client.post(
        f"/api/projects/{p}/documents", files={"file": (name, content)}
    )
    assert response.status_code == 201, response.text
    return response.json()


def start(client, p, d, size=4, overlap=1):
    response = client.post(
        f"/api/projects/{p}/documents/{d}/runs",
        json={"chunk_size": size, "overlap": overlap},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_upload_processing_duplicate_delivery_and_scope(documents_api):
    client, engine, p, q = documents_api
    doc = upload(client, p)
    duplicate = upload(client, p)
    assert (
        doc["id"] != duplicate["id"]
        and doc["content_hash"] == duplicate["content_hash"]
    )
    assert client.get(f"/api/projects/{p}/documents?limit=1").json()["total"] == 2
    job = start(client, p, doc["id"])
    route = f"/api/projects/{p}/documents/{doc['id']}/runs/{job['id']}"
    assert client.get(route + "/chunks").status_code == 409
    assert (
        client.post(
            f"/api/projects/{p}/documents/{doc['id']}/runs", json={}
        ).status_code
        == 409
    )
    process(UUID(job["id"]), engine)
    process(UUID(job["id"]), engine)
    result = client.get(route).json()
    assert (
        result["status"] == "succeeded"
        and result["attempts"] == 1
        and result["chunk_count"] == 3
    )
    chunks = client.get(route + "/chunks?limit=2").json()
    assert chunks["total"] == 3 and [c["text"] for c in chunks["items"]] == [
        "abcd",
        "defg",
    ]
    assert client.get(route + "/chunks?offset=2").json()["items"][0]["text"] == "ghij"
    assert client.get(route.replace(p, q)).status_code == 404
    assert client.get(route.replace(p, q) + "/chunks").status_code == 404
    assert client.post(route.replace(p, q) + "/cancel").status_code == 404
    assert (
        client.get(f"/api/projects/{q}/documents/{doc['id']}/runs").status_code == 404
    )
    assert (
        client.post(
            f"/api/projects/{q}/documents/{doc['id']}/runs", json={}
        ).status_code
        == 404
    )
    assert client.get(f"/api/projects/{q}/documents").json()["total"] == 0
    assert (
        client.get(f"/api/projects/{p}/documents").json()["items"][1]["latest_run"][
            "status"
        ]
        == "succeeded"
    )
    assert "storage_name" not in str(doc) and "execution_token" not in result
    assert start(client, p, doc["id"], 5, 0)["version"] == 2
    assert client.get(route + "/chunks").json()["total"] == 3


@pytest.mark.parametrize(
    "name,content,status",
    [
        ("empty.txt", b"", 422),
        ("space.txt", b" \n", 422),
        ("bad.txt", b"\xff", 422),
        ("null.txt", b"\x00", 422),
        ("file.csv", b"text", 415),
        ("fake.pdf", b"not pdf", 422),
    ],
)
def test_bad_uploads(documents_api, name, content, status):
    client, _, p, _ = documents_api
    assert (
        client.post(
            f"/api/projects/{p}/documents", files={"file": (name, content)}
        ).status_code
        == status
    )
    assert client.get(f"/api/projects/{p}/documents").json()["total"] == 0
    assert list(settings.storage_path.iterdir()) == []


def test_limits_and_one_file(documents_api, monkeypatch):
    client, _, p, _ = documents_api
    monkeypatch.setattr(settings, "max_upload_bytes", 8)
    route = f"/api/projects/{p}/documents"
    assert (
        client.post(route, files={"file": ("large.txt", b"x" * 9)}).status_code == 413
    )
    assert (
        client.post(
            route, files=[("file", ("a.txt", b"a")), ("file", ("b.txt", b"b"))]
        ).status_code
        == 422
    )
    assert client.post(route, content=b"x" * 70000).status_code == 413
    assert client.get(route).json()["total"] == 0
    assert not list(settings.storage_path.iterdir())


def test_pdf_provenance_and_failed_retry(documents_api):
    client, engine, p, _ = documents_api
    doc = upload(client, p, pdf_bytes(["abcde", "fghij"]), "source.pdf")
    job = start(client, p, doc["id"])
    process(UUID(job["id"]), engine)
    route = f"/api/projects/{p}/documents/{doc['id']}/runs/{job['id']}"
    chunks = client.get(route + "/chunks").json()["items"]
    assert [(c["page_number"], c["start_char"], c["text"]) for c in chunks] == [
        (1, 0, "abcd"),
        (1, 3, "de"),
        (2, 0, "fghi"),
        (2, 3, "ij"),
    ]
    new = start(client, p, doc["id"])
    with patch(
        "app.workers.processing.pages", side_effect=ProcessingError("Parsing failed.")
    ):
        process(UUID(new["id"]), engine)
    failed_route = route.replace(job["id"], new["id"])
    assert client.get(failed_route).json()["status"] == "failed"
    assert client.get(failed_route + "/chunks").status_code == 409
    retry = start(client, p, doc["id"])
    process(UUID(retry["id"]), engine)
    assert (
        client.get(route.replace(job["id"], retry["id"])).json()["status"]
        == "succeeded"
    )
    assert client.get(failed_route).json()["status"] == "failed"


def test_cancel_during_processing_and_atomic_failure(documents_api):
    client, engine, p, _ = documents_api
    doc = upload(client, p)
    job = start(client, p, doc["id"])
    route = f"/api/projects/{p}/documents/{doc['id']}/runs/{job['id']}"

    def cancelling(*args):
        yield 1, "abcdefgh", 1, 2
        assert client.post(route + "/cancel").json()["status"] == "cancelled"
        yield 2, "abcdefgh", 2, 2

    with patch("app.workers.processing.pages", cancelling):
        process(UUID(job["id"]), engine)
    assert client.get(route + "/chunks").status_code == 409
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.run_id == UUID(job["id"]))
            )
            == 0
        )
    next_job = start(client, p, doc["id"])

    def failing(*args):
        yield 1, "abcdefgh", 1, 2
        raise ProcessingError("Page two failed.")

    with patch("app.workers.processing.pages", failing):
        process(UUID(next_job["id"]), engine)
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Chunk)
                .where(Chunk.run_id == UUID(next_job["id"]))
            )
            == 0
        )
    cancelled = start(client, p, doc["id"])
    client.post(route.replace(job["id"], cancelled["id"]) + "/cancel")
    process(UUID(cancelled["id"]), engine)
    assert client.get(route.replace(job["id"], cancelled["id"])).json()["attempts"] == 0


def test_bounded_retry_stale_recovery_and_broker_outage(documents_api):
    client, engine, p, _ = documents_api
    doc = upload(client, p)
    job = start(client, p, doc["id"])
    id = UUID(job["id"])
    with pytest.raises(OSError):
        dispatch_once(engine, send=lambda _: (_ for _ in ()).throw(OSError()))
    with Session(engine) as session:
        assert session.get(ProcessingRun, id).status == "queued"
    for attempt in (1, 2, 3):
        with Session(engine) as session:
            session.execute(
                update(ProcessingRun)
                .where(ProcessingRun.id == id)
                .values(
                    status="running",
                    attempts=attempt,
                    execution_token=uuid4(),
                    started_at=now() - timedelta(seconds=181),
                )
            )
            session.commit()
        sent = []
        dispatch_once(engine, send=sent.append)
        assert sent == ([id] if attempt < 3 else [])
    with Session(engine) as session:
        result = session.get(ProcessingRun, id)
        assert result.status == "failed" and result.execution_token is None
    retry = start(client, p, doc["id"])
    with patch("app.workers.processing.pages", side_effect=OSError()):
        for _ in range(5):
            process(UUID(retry["id"]), engine)
    with Session(engine) as session:
        result = session.get(ProcessingRun, UUID(retry["id"]))
        assert result.status == "failed" and result.attempts == 3


@pytest.mark.parametrize(
    "config",
    [
        {"chunk_size": 0},
        {"chunk_size": 4, "overlap": 4},
        {"chunk_size": 5, "overlap": -1},
        {"chunk_size": True},
        {"chunk_size": 100001},
    ],
)
def test_settings_validation(documents_api, config):
    client, _, p, _ = documents_api
    doc = upload(client, p)
    assert (
        client.post(
            f"/api/projects/{p}/documents/{doc['id']}/runs", json=config
        ).status_code
        == 422
    )


def test_concurrent_duplicate_delivery(documents_api):
    from concurrent.futures import ThreadPoolExecutor

    client, engine, p, _ = documents_api
    doc = upload(client, p)
    job = start(client, p, doc["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(process, UUID(job["id"]), engine) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    with Session(engine) as session:
        result = session.get(ProcessingRun, UUID(job["id"]))
        assert result.status == "succeeded" and result.attempts == 1
        assert result.chunk_count == 3


def test_recovered_attempt_fences_old_worker(documents_api):
    client, engine, p, _ = documents_api
    doc = upload(client, p)
    job = start(client, p, doc["id"])
    id = UUID(job["id"])

    def interrupted(*args):
        with Session(engine) as session:
            session.execute(
                update(ProcessingRun)
                .where(ProcessingRun.id == id)
                .values(started_at=now() - timedelta(seconds=181))
            )
            session.commit()
        dispatch_once(engine, send=lambda _: None)
        with patch(
            "app.workers.processing.pages",
            return_value=iter([(None, "new text", 1, 1)]),
        ):
            process(id, engine)
        yield None, "obsolete output", 1, 1

    with patch("app.workers.processing.pages", interrupted):
        process(id, engine)
    with Session(engine) as session:
        result = session.get(ProcessingRun, id)
        assert result.status == "succeeded" and result.attempts == 2
        texts = session.scalars(
            select(Chunk.text).where(Chunk.run_id == id).order_by(Chunk.ordinal)
        ).all()
        assert texts == ["new ", " tex", "xt"]


def test_upload_storage_failure_and_ambiguous_commit(documents_api):
    from sqlalchemy.exc import SQLAlchemyError

    client, engine, p, _ = documents_api
    route = f"/api/projects/{p}/documents"
    with patch("app.services.documents.os.fsync", side_effect=OSError("private path")):
        response = client.post(route, files={"file": ("source.txt", b"text")})
    assert response.status_code == 503 and "private" not in response.text
    assert not list(settings.storage_path.iterdir())
    assert client.get(route).json()["total"] == 0
    original = Session.commit

    def ambiguous(session):
        original(session)
        raise SQLAlchemyError("private database details")

    with patch.object(Session, "commit", ambiguous):
        response = client.post(route, files={"file": ("source.txt", b"text")})
    assert response.status_code == 503 and "private" not in response.text
    with Session(engine) as session:
        result = session.scalar(select(Document).where(Document.project_id == UUID(p)))
        assert (settings.storage_path / result.storage_name).read_bytes() == b"text"


def test_extra_file_fields_rejected(documents_api):
    client, _, p, _ = documents_api
    response = client.post(
        f"/api/projects/{p}/documents",
        files=[("file", ("a.txt", b"a")), ("other", ("b.txt", b"b"))],
    )
    assert response.status_code == 422
    assert client.get(f"/api/projects/{p}/documents").json()["total"] == 0


def test_scanned_page_in_mixed_pdf_requires_ocr(tmp_path):
    from pypdf import PdfReader
    from pypdf.generic import NumberObject

    writer = PdfWriter()
    reader = PdfReader(BytesIO(pdf_bytes(["Some visible text"])))
    writer.add_page(reader.pages[0])
    page = writer.add_blank_page(width=300, height=300)
    image = DecodedStreamObject()
    image.set_data(b"\x00\x00\x00")
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Im0"): writer._add_object(image)}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(b"q 100 0 0 100 0 0 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(content)
    path = tmp_path / "mixed.pdf"
    writer.write(path)
    with pytest.raises(ProcessingError, match="OCR"):
        list(pages(path, "application/pdf"))


def test_body_limit_without_content_length(documents_api, monkeypatch):
    client, _, p, _ = documents_api
    monkeypatch.setattr(settings, "max_upload_bytes", 8)
    response = client.post(
        f"/api/projects/{p}/documents",
        content=iter(
            [
                b'--test\r\nContent-Disposition: form-data; name="file"; filename="large.txt"\r\n\r\n',
                b"x" * 70000,
                b"\r\n--test--\r\n",
            ]
        ),
        headers={"Content-Type": "multipart/form-data; boundary=test"},
    )
    assert response.status_code == 413
    assert client.get(f"/api/projects/{p}/documents").json()["total"] == 0


def test_chunk_output_limit_fails_without_publishing(documents_api, monkeypatch):
    client, engine, p, _ = documents_api
    doc = upload(client, p)
    job = start(client, p, doc["id"])
    monkeypatch.setattr("app.workers.processing.MAX_CHUNKS", 2)
    process(UUID(job["id"]), engine)
    with Session(engine) as session:
        result = session.get(ProcessingRun, UUID(job["id"]))
        assert result.status == "failed" and "chunk limit" in result.error
        assert (
            session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.run_id == result.id)
            )
            == 0
        )


def test_cleanup_failure_does_not_expose_storage_details(documents_api):
    from pathlib import Path

    client, _, p, _ = documents_api
    with (
        patch(
            "app.services.documents.os.fsync", side_effect=OSError("private directory")
        ),
        patch.object(Path, "unlink", side_effect=PermissionError("private directory")),
    ):
        response = client.post(
            f"/api/projects/{p}/documents", files={"file": ("source.txt", b"text")}
        )
    assert response.status_code == 503 and "private" not in response.text
    assert client.get(f"/api/projects/{p}/documents").json()["total"] == 0
