"""Spec 0008 D2: Maximum OCR pages defaults to 100; saved values run as saved."""

from app.schemas.ingestion import ExtractNodeV2


def extract_node(**ocr) -> ExtractNodeV2:
    return ExtractNodeV2(
        id="extract",
        type="extract",
        strategy="auto",
        ocr={"mode": "auto", **ocr},
        config_version="layout-ocr-v3",
    )


def test_new_extract_nodes_read_up_to_100_scanned_pages():
    assert extract_node().ocr.max_pages == 100


def test_a_saved_page_limit_survives_a_save_round_trip():
    saved = extract_node(max_pages=50).model_dump(mode="json")
    assert saved["ocr"]["max_pages"] == 50
    assert ExtractNodeV2.model_validate(saved).ocr.max_pages == 50
