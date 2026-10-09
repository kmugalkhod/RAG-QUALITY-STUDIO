"""v3 website reading: whole tables, no reference lists (spec 0007, slice 3)."""

from __future__ import annotations

from app.pipelines.web_content import extract_canonical_sections
from app.services import website_ingestion
from app.schemas.ingestion import ExtractNodeV2

PAGE = b"""
<html><body><main>
<h1>Rates</h1>
<p>The rates change every year.<sup class="reference"><a href="#c1">[1]</a></sup></p>
<table>
  <tr><th></th><th>21 and over</th><th>Under 18</th></tr>
  <tr><td>April 2026</td><td>&pound;12.71</td><td>&pound;8</td></tr>
  <tr><td>April 2025</td><td>&pound;12.21<br>(old)</td><td><table><tr><td>&pound;7.55</td></tr></table></td></tr>
</table>
<table class="infobox"><tr><th>Elevation</th><td>8,848.86 m</td></tr></table>
<h2>History</h2>
<p>Rates started in 1999.</p>
<h2>References</h2>
<ol class="references"><li>Retrieved 1 May 2026.</li></ol>
<p>Archived copy of the guidance.</p>
<h2>Eligibility</h2>
<p>Workers aged 21 or over qualify.</p>
<div class="reflist"><p>Another citation list.</p></div>
</main></body></html>
"""


def texts(sections):
    return [section.text for section in sections]


def test_v3_keeps_tables_as_rows_with_a_header():
    sections = extract_canonical_sections(PAGE, v3=True)
    tables = [s for s in sections if s.block_type == "table"]
    assert tables[0].text.splitlines() == [
        "|  | 21 and over | Under 18 |",
        "| --- | --- | --- |",
        "| April 2026 | £12.71 | £8 |",
        "| April 2025 | £12.21 (old) | £7.55 |",
    ]
    assert tables[0].attributes["table"]["header_row"] == [
        "",
        "21 and over",
        "Under 18",
    ]
    assert tables[0].path == ("Rates",)
    assert "| Elevation | 8,848.86 m |" in tables[1].text


def test_v3_leaves_out_reference_lists_and_citation_markers():
    joined = "\n".join(texts(extract_canonical_sections(PAGE, v3=True)))
    assert "[1]" not in joined
    assert "Retrieved" not in joined
    assert "Archived copy" not in joined
    assert "Another citation list" not in joined
    assert "References" not in joined
    # Content after the references section resumes at the next heading.
    assert "Workers aged 21 or over qualify." in joined
    assert "Rates started in 1999." in joined


def test_without_v3_reading_is_unchanged():
    v2 = texts(extract_canonical_sections(PAGE))
    assert "£12.71" in v2 and "April 2026" in v2
    assert "Retrieved 1 May 2026." in v2
    assert not any(text.startswith("|") for text in v2)


def test_v3_has_its_own_website_processing_identity():
    from app.schemas.ingestion import CleanNodeV2, SectionTokenChunkNodeV2
    from app.ingestion_content.cleaning import default_structure_steps

    clean = CleanNodeV2(
        id="clean",
        type="clean",
        profile="structure-aware-v1",
        config_version="structure-clean-v1",
        steps=default_structure_steps(),
    )
    chunk = SectionTokenChunkNodeV2.model_validate(
        {
            "id": "chunk",
            "type": "chunk",
            "algorithm": "section_token",
            "target_tokens": 600,
            "maximum_tokens": 800,
            "overlap_tokens": 80,
        }
    )
    v2 = ExtractNodeV2(
        id="extract", type="extract", strategy="auto", config_version="layout-ocr-v2"
    )
    v3 = ExtractNodeV2(
        id="extract", type="extract", strategy="auto", config_version="layout-ocr-v3"
    )
    _, v2_hash, v2_parser = website_ingestion.website_processing_identity(
        chunk, clean, v2
    )
    _, v3_hash, v3_parser = website_ingestion.website_processing_identity(
        chunk, clean, v3
    )
    assert v2_hash != v3_hash
    assert v2_parser.startswith("html-main-v2/")
    assert v3_parser.startswith("html-main-v3.1/")


def test_v3_keeps_inline_reference_links_and_whole_sentences():
    """Real-source re-run: Python docs mark ordinary links with class "reference",
    and a citation marker must not split its sentence."""

    page = b"""<html><body><main><h1>Control flow</h1>
<p>The <a class="reference internal" href="#pass"><code>pass</code></a> statement
does nothing. Use <a class="reference external" href="#d"><code>collections.deque</code></a>
for queues.</p>
<p>Python 3.0, released in 2008,<sup class="reference"><a href="#c">[5]</a></sup>
was a major revision.</p>
</main></body></html>"""
    sections = texts(extract_canonical_sections(page, v3=True))
    joined = " ".join(" ".join(sections).split())
    assert "The pass statement does nothing." in joined
    assert "Use collections.deque for queues." in joined
    assert "[5]" not in joined
    # The sentence around the citation marker stays in one block.
    assert any(
        "released in 2008," in s and "was a major revision" in s for s in sections
    )
