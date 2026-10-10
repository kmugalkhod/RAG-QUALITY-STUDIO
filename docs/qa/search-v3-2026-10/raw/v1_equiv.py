"""Spec 0010 slice 1: v1 chunks equal the previous code's on every real file; v2 stats.

Extracts each harness file with layout-ocr-v5 (no provider calls), cleans with the
structure-aware profile and chunks with section-token and parent-child, v1 and v2.
/tmp/chunking_old.py is `git show 359e812:backend/app/ingestion_content/chunking.py`.
Run in the backend container: PYTHONPATH=/app python v1_equiv.py
"""
import importlib.util
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import engine
from app.ingestion_content import chunk_cleaned_document, clean_document, cleaner_for_node
from app.ingestion_content.cleaning import default_structure_steps
from app.ingestion_content.extractors.pdf import detect_media_type, extract_document
from app.models.document import Document
from app.schemas.ingestion import CleanNodeV2, ExtractNodeV2, ParentChildChunkNodeV2, SectionTokenChunkNodeV2
from app.services.artifact_storage import materialize

spec = importlib.util.spec_from_file_location("chunking_old", "/tmp/chunking_old.py")
old = importlib.util.module_from_spec(spec)
sys.modules['chunking_old'] = old
spec.loader.exec_module(old)

MEDIA = {".pdf": "application/pdf", ".txt": "text/plain",
         ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
         ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
state = json.load(open("/tmp/rs/state.json"))
docs = {**state["documents"], **state.get("documents_v4", {}), **state.get("documents_v5", {})}
only = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
clean = CleanNodeV2(id="clean", type="clean", profile="structure-aware-v1",
                    config_version="structure-clean-v1", steps=deepcopy(default_structure_steps()))
extract = ExtractNodeV2(id="extract", type="extract", strategy="auto",
                        ocr={"mode": "auto", "languages": ["eng"], "max_pages": 100},
                        tables="preserve", config_version="layout-ocr-v5")
base = {"id": "chunk", "type": "chunk"}
profiles = {
    "section": lambda v: SectionTokenChunkNodeV2.model_validate({**base, "algorithm": "section_token", "config_version": f"section-token-{v}"}),
    "parent": lambda v: ParentChildChunkNodeV2.model_validate({**base, "algorithm": "parent_child", "config_version": f"parent-child-{v}"}),
}
work = Path("/tmp/v1eq"); work.mkdir(exist_ok=True)
report = {}
skipped = []
with Session(engine) as session:
    for key, info in sorted(docs.items()):
        if only and key not in only:
            continue
        suffix = Path(info["filename"]).suffix.lower()
        if suffix not in MEDIA:
            continue
        document = session.get(Document, info["id"])
        copy = work / f"input{suffix}"
        with materialize(document) as path:
            shutil.copyfile(path, copy)
        extracted = None
        for attempt in range(2):
            try:
                extracted, extractor = extract_document(copy, detect_media_type(copy, MEDIA[suffix]), Path(info["filename"]).stem, extract)
                break
            except Exception as error:  # an OCR timeout under load; retry once
                print(key, info["filename"], "extraction failed:", type(error).__name__, error, flush=True)
        if extracted is None:
            skipped.append(key)
            continue
        cleaned = clean_document(extracted, clean, cleaner_for_node(clean), extractor_version=extractor, configuration_hash="a" * 64)
        row = {}
        for name, make in profiles.items():
            v1 = chunk_cleaned_document(cleaned, make("v1"))
            reference, reference_spans = old.chunk_structured_document(cleaned, make("v1"))
            assert v1.chunks == reference and v1.spans == reference_spans, f"{key} {name} v1 differs"
            v2 = chunk_cleaned_document(cleaned, make("v2"))
            searchable = lambda r: [c for c in r.chunks if c.chunk_role != "parent"]
            row[name] = {
                "v1_chunks": len(searchable(v1)), "v2_chunks": len(searchable(v2)),
                "v1_under_40": sum(c.token_count < 40 for c in searchable(v1)),
                "v2_under_40": sum(c.token_count < 40 for c in searchable(v2)),
                "callout_chunk_tokens": next((c.token_count for c in searchable(v2) if "381 d" in c.text), None),
            }
        report[key] = row
        print(key, info["filename"], json.dumps(row), flush=True)
json.dump(report, open("/tmp/v1eq/report.json", "w"), indent=1)
print("v1 identical to previous code on", len(report), "files; skipped", skipped)
