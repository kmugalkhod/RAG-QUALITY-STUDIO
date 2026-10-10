"""Free, local extractor snapshots for spec 0008 (no provider calls, no runs).

Run inside the backend container:

    python scripts/real_source/extract_baseline.py export WORK DOC_ID...
    python scripts/real_source/extract_baseline.py extract WORK VERSION OUT.json

``export`` copies stored (encrypted) project documents to WORK/files through the
app's own storage code. ``extract`` runs ``extract_document`` on every file in
WORK/files with the recommended Extract settings at the given extractor version
and writes every block, page origin and quality finding, so two versions can be
compared block by block.
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ingestion_content.extractors.pdf import detect_media_type, extract_document  # noqa: E402
from app.schemas.ingestion import ExtractNodeV2  # noqa: E402

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def export(work: Path, document_ids: list[str]) -> None:
    from sqlalchemy.orm import Session

    from app.db.session import engine
    from app.models.document import Document
    from app.services.artifact_storage import materialize

    target = work / "files"
    target.mkdir(parents=True, exist_ok=True)
    with Session(engine) as session:
        for document_id in document_ids:
            document = session.get(Document, document_id)
            with materialize(document) as path:
                data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != document.content_hash:
                raise SystemExit(f"{document.filename}: content hash differs.")
            (target / document.filename).write_bytes(data)
            print(document.filename, len(data))


def settings(version: str) -> ExtractNodeV2:
    # The recommended values (spec 0008 Part A), with Maximum OCR pages at 100 (D2).
    return ExtractNodeV2(
        id="extract",
        type="extract",
        strategy="auto",
        ocr={"mode": "auto", "languages": ["eng"], "max_pages": 100},
        tables="preserve",
        config_version=version,
    )


def extract(work: Path, version: str, out: Path) -> None:
    result = {"config_version": version, "files": {}}
    scratch = work / "scratch"
    for path in sorted((work / "files").iterdir()):
        media_type = MEDIA_TYPES.get(path.suffix.lower())
        if media_type is None:
            continue
        # Copy so a file name never changes the extractor's view of the bytes.
        scratch.mkdir(exist_ok=True)
        copy = scratch / f"input{path.suffix.lower()}"
        shutil.copyfile(path, copy)
        detected = detect_media_type(copy, media_type)
        document, extractor = extract_document(
            copy, detected, path.stem, settings(version)
        )
        payload = document.model_dump(mode="json")
        result["files"][path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "extractor": extractor,
            "digest": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "measurements": payload["measurements"],
            "findings": payload["findings"],
            "pages": [
                {
                    k: page[k]
                    for k in (
                        "page_number",
                        "origin",
                        "character_count",
                        "block_count",
                        "fallback_reason",
                    )
                }
                for page in payload["pages"]
            ],
            "blocks": [
                {
                    "ordinal": b["ordinal"],
                    "type": b["type"],
                    "page": b["page_number"],
                    "heading_path": b["heading_path"],
                    "attributes": b["attributes"],
                    "text": b["text"],
                }
                for b in payload["blocks"]
            ],
        }
        print(path.name, extractor, len(payload["blocks"]), "blocks", flush=True)
    shutil.rmtree(scratch, ignore_errors=True)
    out.write_text(
        json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    command, work = sys.argv[1], Path(sys.argv[2])
    if command == "export":
        export(work, sys.argv[3:])
    elif command == "extract":
        extract(work, sys.argv[3], Path(sys.argv[4]))
    else:
        raise SystemExit(f"Unknown command {command}.")
