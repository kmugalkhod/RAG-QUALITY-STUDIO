"""Remote-source ingestion discovery, persistence, and publication advancement."""

import itertools
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.confluence import ConfluenceConnector
from app.connectors.notion import NotionConnector
from app.connectors.s3 import S3Connector
from app.connectors.safe_http import url_origin
from app.connectors.website import (
    PreviewOutcome,
    PriorWebsiteRevision,
    WebsiteArtifact,
    WebsiteConnector,
)
from app.core.connection_secrets import ConnectionKeyring
from app.core.config import settings
from app.models.ingestion import IngestionRun
from app.models.document import Chunk, Document, ProcessingRun
from app.ingestion_content.duplicates import DuplicateCandidate, classify_duplicates
from app.ingestion_content.processing import IngestionStageError
from app.ingestion_content.quality import excludes_failed_items
from app.pipelines.parsing import ProcessingError
from app.models.source import (
    IndexSourceRevision,
    SourceItem,
    SourceRevision,
    SourceSnapshotMember,
    WebsiteCrawlFrontier,
    WebsiteRunItem,
)
from app.schemas.ingestion import IngestionExecution
from app.services import (
    artifact_storage,
    connections,
    confluence_ingestion,
    ingestion_execution,
    indexes,
    notion_ingestion,
    s3_ingestion,
    source_snapshots,
    source_artifacts,
    website_crawl,
    website_ingestion,
)
from app.workers.processing import now


REMOTE_SOURCE_KINDS = frozenset({"website", "s3", "notion", "confluence"})


def _apply_duplicate_policy(
    session, run_id, memberships, clean, source_kind, also_found=None
):
    """Keep one membership per duplicate group.

    `also_found` collects, per kept source item id, where excluded copies were
    found, so a merged index keeps every source a page came from.
    """
    policy = getattr(clean, "duplicate_policy", None)
    if policy is None:
        return memberships
    candidates = []
    by_identity = {}
    for membership in memberships:
        source_node_id, item, revision = membership
        chunks = session.scalars(
            select(Chunk)
            .where(Chunk.run_id == revision.processing_run_id)
            .order_by(Chunk.ordinal)
        ).all()
        candidate = DuplicateCandidate(
            identity=item.canonical_location,
            source_kind=source_kind,
            raw_hash=revision.content_hash,
            cleaned_hash=revision.extracted_hash,
            text="\n".join(chunk.text for chunk in chunks),
            stable_order=int(item.created_at.timestamp() * 1_000_000),
        )
        candidates.append(candidate)
        by_identity[candidate.identity] = membership
    decisions = classify_duplicates(candidates, policy)
    retained = []
    for identity, decision in decisions.items():
        membership = by_identity[identity]
        row = session.scalar(
            select(WebsiteRunItem).where(
                WebsiteRunItem.run_id == run_id,
                WebsiteRunItem.source_node_id == membership[0],
                WebsiteRunItem.source_revision_id == membership[2].id,
            )
        )
        if row is not None:
            row.duplicate_decision = decision.as_dict()
            if decision.outcome == "excluded":
                row.outcome = "excluded"
                row.reason = (
                    f"Duplicate of {decision.retained_identity} by "
                    f"{decision.method} ({decision.similarity:.3f})."
                )
        if decision.outcome == "retained":
            retained.append(membership)
        elif also_found is not None and decision.retained_identity in by_identity:
            kept = by_identity[decision.retained_identity]
            # Places the excluded page was itself found move to the kept page.
            also_found.setdefault(kept[1].id, []).extend(
                also_found.pop(membership[1].id, [])
            )
            also_found[kept[1].id].append(
                {
                    "source_node_id": membership[0],
                    "canonical_location": identity,
                    "reason": decision.method,
                }
            )
    return retained


def fail_run(
    session: Session, job: IngestionRun, message: str, node_type: str | None = None
):
    source_snapshots.mark_terminal(session, job.source_snapshot_id, "failed", message)
    job.status = "failed"
    job.execution_token = None
    job.error = message
    job.updated_at = job.finished_at = now()
    ingestion_execution.mark_terminal(session, job.id, "failed", node_type=node_type)


def _prior_body_loader(db_engine, document_id):
    """Load a stored page only if the crawl reuses it, keeping bodies out of memory."""

    def load() -> bytes:
        try:
            with Session(db_engine) as session:
                document = session.get(Document, document_id)
                if document is None:
                    raise FileNotFoundError
                return artifact_storage.read(document)
        except OSError as exc:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="prior_artifact_unavailable",
                    message="A prior website artifact is unavailable for safe refresh.",
                    retryable=False,
                )
            ) from exc

    return load


def _website_priors(session, job, db_engine):
    index_id = job.snapshot.get("prior_ready_index_id")
    if not index_id:
        return {}, {}
    rows = session.execute(
        select(IndexSourceRevision.source_node_id, SourceItem, SourceRevision)
        .select_from(IndexSourceRevision)
        .join(SourceItem, SourceItem.id == IndexSourceRevision.source_item_id)
        .join(
            SourceRevision, SourceRevision.id == IndexSourceRevision.source_revision_id
        )
        .where(
            IndexSourceRevision.index_id == UUID(index_id),
            IndexSourceRevision.project_id == job.project_id,
            SourceItem.kind == "website",
        )
    ).all()
    revisions = {
        item.canonical_location: (revision, source_node_id)
        for source_node_id, item, revision in rows
    }
    priors = {
        location: PriorWebsiteRevision(
            media_type=revision.media_type,
            etag=revision.etag,
            last_modified=revision.last_modified,
            fetched_at=revision.fetched_at,
            loader=_prior_body_loader(db_engine, revision.document_id),
        )
        for location, (revision, _) in revisions.items()
    }
    return priors, revisions


def _website_snapshot_priors(session, job):
    rows = session.execute(
        select(SourceSnapshotMember.source_node_id, SourceItem, SourceRevision)
        .select_from(SourceSnapshotMember)
        .join(SourceItem, SourceItem.id == SourceSnapshotMember.source_item_id)
        .join(
            SourceRevision,
            SourceRevision.id == SourceSnapshotMember.source_revision_id,
        )
        .where(
            SourceSnapshotMember.snapshot_id == job.source_snapshot_id,
            SourceSnapshotMember.project_id == job.project_id,
        )
        .order_by(SourceSnapshotMember.ordinal)
    ).all()
    if not rows:
        raise ConnectorFailure(
            ConnectorIssue(
                code="snapshot_members_unavailable",
                message="The selected source snapshot has no reusable Website pages.",
                retryable=False,
            )
        )
    revisions = {
        item.canonical_location: (revision, source_node_id)
        for source_node_id, item, revision in rows
    }
    priors = {}
    for location, (revision, _) in revisions.items():
        try:
            document = session.get(Document, revision.document_id)
            if document is None:
                raise FileNotFoundError
            content = artifact_storage.read(document)
        except OSError as exc:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="snapshot_artifact_unavailable",
                    message="A source snapshot artifact is unavailable for rebuilding.",
                    retryable=True,
                )
            ) from exc
        priors[location] = PriorWebsiteRevision(
            content=content,
            media_type=revision.media_type,
            etag=revision.etag,
            last_modified=revision.last_modified,
        )
    return priors, revisions


# Returned instead of in-memory results when the pages are in the run's frontier.
CRAWLED = object()


def _discover_website(run_id, token, db_engine, connector_factory):
    """Snapshot reuse returns in-memory results; a refresh crawls into the frontier.

    Returns None as results when the crawl was stopped by cancellation or fencing.
    """
    with Session(db_engine) as session:
        job = session.get(IngestionRun, run_id)
        execution = IngestionExecution.model_validate(job.snapshot["execution"])
        source_input = job.snapshot.get("source_input") or {}
        if source_input.get("kind") == "snapshot":
            priors, revisions = _website_snapshot_priors(session, job)
        else:
            priors, revisions = _website_priors(session, job, db_engine)
    if source_input.get("kind") == "snapshot" or job.snapshot.get("reuse_stored"):
        results = []
        for source in [node for node in execution.nodes if node.type == "source"]:
            if not ingestion_execution.transition(
                db_engine, run_id, node_id=source.id, execution_token=token
            ):
                return execution, revisions, results
            outcomes = []
            artifacts = []
            for location, (revision, source_node_id) in revisions.items():
                if source_node_id != source.id:
                    continue
                prior = priors[location]
                outcomes.append(
                    PreviewOutcome(
                        external_id=location,
                        display_name=location,
                        canonical_location=location,
                        media_type=revision.media_type,
                        status="included",
                        reason="Source snapshot page selected for offline index building.",
                        size_bytes=revision.size_bytes,
                        depth=(revision.provenance or {}).get("depth"),
                        provider_revision=revision.provider_revision,
                    )
                )
                artifacts.append(
                    WebsiteArtifact(
                        canonical_location=location,
                        content=prior.content,
                        media_type=prior.media_type,
                        etag=prior.etag,
                        last_modified=prior.last_modified,
                        validator_unchanged=True,
                        depth=(revision.provenance or {}).get("depth") or 0,
                    )
                )
            results.append((source.id, outcomes, artifacts))
        return execution, revisions, results
    if not _crawl_website(
        run_id, token, db_engine, connector_factory, job, execution, priors
    ):
        return execution, revisions, None
    return execution, revisions, CRAWLED


def _crawl_website(run_id, token, db_engine, connector_factory, job, execution, priors):
    """Fetch every Website source into the run's frontier; resumable per page.

    With several sources, a whole-site failure that retrying cannot fix ends
    only that source; the run carries its last good pages forward. Sources
    whose allowed origins do not overlap crawl at the same time, up to
    `website_run_source_concurrency`; sources sharing an origin crawl one
    after another so each origin keeps a single request rate.
    """
    sources = [node for node in execution.nodes if node.type == "source"]
    refresh_only = _refresh_only(job)
    pending = [
        source
        for source in sources
        # Not refreshed sources keep their pages from the current ready index.
        if (refresh_only is None or source.id in refresh_only)
        and not ((job.crawl_state or {}).get(source.id) or {}).get("complete")
    ]
    if not pending:
        return True
    isolate = len(sources) >= 2
    lanes = _origin_lanes(pending)
    if len(lanes) == 1 or settings.website_run_source_concurrency == 1:
        for source in pending:
            if not ingestion_execution.transition(
                db_engine, run_id, node_id=source.id, execution_token=token
            ):
                return False
            if not _crawl_source(
                run_id,
                token,
                db_engine,
                connector_factory,
                job,
                source,
                priors,
                isolate,
            ):
                return False
        return True

    if not ingestion_execution.start_nodes(
        db_engine, run_id, [source.id for source in pending], execution_token=token
    ):
        return False
    stop = threading.Event()

    def crawl_lane(lane):
        for source in lane:
            if stop.is_set():
                return False
            if not _crawl_source(
                run_id,
                token,
                db_engine,
                connector_factory,
                job,
                source,
                priors,
                isolate,
                stop,
            ):
                return False
        return True

    workers = min(settings.website_run_source_concurrency, len(lanes))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(crawl_lane, lane) for lane in lanes]
        error = None
        completed = True
        for future in as_completed(futures):
            try:
                if not future.result():
                    completed = False
                    stop.set()
            except BaseException as exc:  # re-raised once every lane stopped
                stop.set()
                error = error or exc
    if error is not None:
        raise error
    return completed


def _origin_lanes(sources):
    """Group sources whose allowed origins overlap, keeping pipeline order."""
    lanes: list[tuple[set[str], list]] = []
    for source in sources:
        origins = {url_origin(str(value)) for value in source.config.allowed_origins}
        joined = [lane for lane in lanes if lane[0] & origins]
        merged_origins = set(origins).union(*(lane[0] for lane in joined))
        merged = sorted(
            [node for lane in joined for node in lane[1]] + [source],
            key=sources.index,
        )
        lanes = [lane for lane in lanes if lane not in joined]
        lanes.append((merged_origins, merged))
    ordered = sorted(lanes, key=lambda lane: sources.index(lane[1][0]))
    return [lane[1] for lane in ordered]


class _StoppableStore:
    """A crawl store that refuses further pages once another source stopped the run."""

    def __init__(self, store, stop):
        self._store = store
        self._stop = stop

    def __getattr__(self, name):
        return getattr(self._store, name)

    def commit(self, *args, **kwargs):
        if self._stop.is_set():
            return False
        return self._store.commit(*args, **kwargs)


def _crawl_source(
    run_id, token, db_engine, connector_factory, job, source, priors, isolate, stop=None
):
    # The policy recorded at run creation, never one re-resolved from
    # current server settings, so recovery and retries keep the same limits.
    policy = (job.snapshot.get("fetch_policies") or {}).get(source.id)
    if policy is None:
        raise ConnectorFailure(
            ConnectorIssue(
                code="missing_fetch_policy",
                message="This run has no recorded Website fetch limits. Start a new run.",
                retryable=False,
            )
        )
    store = website_crawl.RunCrawlStore(db_engine, run_id, token, source.id)
    connector = connector_factory() if connector_factory else WebsiteConnector()
    try:
        crawled = connector.crawl(
            source.config,
            policy,
            priors,
            store if stop is None else _StoppableStore(store, stop),
        )
    except ConnectorFailure as exc:
        if not isolate or exc.issue.retryable:
            raise
        return store.mark_failed(exc.issue)
    if not crawled:
        return False
    return store.mark_complete()


OUTCOMES_STATE = "__outcomes__"


def _refresh_only(job):
    """Source node ids a run refreshes, or None when it refreshes every source."""
    selected = (job.snapshot.get("source_input") or {}).get("source_node_ids")
    return set(selected) if selected else None


def _failed_sources(crawl_state, execution):
    """Source node id -> recorded whole-site failure, for this run's sources."""
    return {
        node.id: state["failed"]
        for node in execution.nodes
        if node.type == "source"
        and isinstance(state := (crawl_state or {}).get(node.id), dict)
        and state.get("failed")
    }


PROCESSING_STATE = "__processing__"


def _process_crawled(run_id, token, db_engine, execution, prior_revisions):
    """Turn each fetched page into a source revision, one fenced commit per page."""
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    clean = next(node for node in execution.nodes if node.type == "clean")
    extract = next(node for node in execution.nodes if node.type == "extract")
    exclude_failed = excludes_failed_items(getattr(extract, "quality_policy", None))
    worker_engine = db_engine.execution_options(isolation_level="READ COMMITTED")

    def prior_body(*locations):
        # Unchanged pages were not stored again during the crawl; the prior is
        # keyed by the queued URL, with the final URL as a fallback.
        entry = next(
            (prior_revisions[url] for url in locations if url in prior_revisions),
            None,
        )
        if entry is None:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="prior_artifact_unavailable",
                    message="A prior website artifact is unavailable for safe refresh.",
                    retryable=False,
                )
            )
        return _prior_body_loader(db_engine, entry[0].document_id)()

    def heartbeat() -> bool:
        """Show the run is alive during the long fingerprint pass."""
        with Session(worker_engine) as session:
            job = session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return False
            job.updated_at = now()
            session.commit()
        return True

    with Session(worker_engine) as session:
        job = session.get(IngestionRun, run_id)
        processing = dict((job.crawl_state or {}).get(PROCESSING_STATE) or {})
        # A failed source's pages are not used; its last good pages are kept.
        failed_sources = list(_failed_sources(job.crawl_state, execution))
        pending = session.scalars(
            select(WebsiteCrawlFrontier.id)
            .where(
                WebsiteCrawlFrontier.run_id == run_id,
                WebsiteCrawlFrontier.status == "fetched",
                WebsiteCrawlFrontier.source_revision_id.is_(None),
                WebsiteCrawlFrontier.source_node_id.not_in(failed_sources),
            )
            .order_by(WebsiteCrawlFrontier.source_node_id, WebsiteCrawlFrontier.ordinal)
        ).all()
    if not pending:
        return True
    if "fingerprints" not in processing:
        # Repeated site chrome is measured once per source across its fetched
        # pages, so one site's navigation never changes how another site's
        # pages are cleaned. It is recorded so pages processed after a
        # recovery are cleaned identically.
        fingerprints = {}
        main_step = next(
            (
                step
                for step in getattr(clean, "steps", None) or []
                if step.enabled and step.type == "website_main_content"
            ),
            None,
        )
        if (
            getattr(clean, "profile", None) == "structure-aware-v1"
            and main_step is not None
            and main_step.remove_repeated_site_chrome
        ):
            from app.ingestion_content.cleaning import website_text_fingerprints

            extracted = itertools.count(1)

            def documents(rows):
                # Pages are extracted one at a time; extraction is repeated
                # per page later rather than keeping every document in memory.
                for row in rows:
                    if next(extracted) % 25 == 0 and not heartbeat():
                        raise _Fenced
                    yield website_ingestion.canonical_extracted_document(
                        website_crawl.page_artifact(row, prior_body), clean, extract
                    )

            with Session(worker_engine) as session:
                rows = session.scalars(
                    select(WebsiteCrawlFrontier)
                    .where(
                        WebsiteCrawlFrontier.run_id == run_id,
                        WebsiteCrawlFrontier.status == "fetched",
                        WebsiteCrawlFrontier.source_node_id.not_in(failed_sources),
                    )
                    .order_by(
                        WebsiteCrawlFrontier.source_node_id,
                        WebsiteCrawlFrontier.ordinal,
                    )
                ).all()
                by_source = {}
                for row in rows:
                    by_source.setdefault(row.source_node_id, []).append(row)
                try:
                    fingerprints = {
                        source_node_id: sorted(
                            website_text_fingerprints(
                                documents(source_rows), main_step.minimum_page_ratio
                            )
                        )
                        for source_node_id, source_rows in by_source.items()
                    }
                except _Fenced:
                    return False
        with Session(worker_engine) as session:
            job = session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return False
            processing["fingerprints"] = fingerprints
            job.crawl_state = {**(job.crawl_state or {}), PROCESSING_STATE: processing}
            session.commit()
    recorded = processing["fingerprints"]

    def fingerprints_for(source_node_id):
        # Runs recorded before per-source fingerprints stored one shared list.
        if isinstance(recorded, list):
            return set(recorded)
        return set(recorded.get(source_node_id) or [])

    def phase_callback(node_type):
        return ingestion_execution.transition(
            db_engine, run_id, node_type=node_type, execution_token=token
        )

    for row_id in pending:
        released = None
        with Session(worker_engine) as session:
            job = session.scalar(
                select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
            )
            if job.status != "running" or job.execution_token != token:
                return False
            row = session.get(WebsiteCrawlFrontier, row_id)
            if row.source_revision_id is not None:
                continue
            artifact = website_crawl.page_artifact(row, prior_body)
            prior_entry = prior_revisions.get(artifact.canonical_location)
            try:
                # A savepoint keeps a failed page's partial rows out of the run.
                with session.begin_nested():
                    source_item, revision, classification, extracted_hash, _stored = (
                        website_ingestion.persist_artifact(
                            session,
                            job.project_id,
                            artifact,
                            chunk,
                            clean,
                            prior_entry[0] if prior_entry else None,
                            phase_callback,
                            extract,
                            None,
                            fingerprints_for(row.source_node_id),
                        )
                    )
            except (ProcessingError, IngestionStageError) as exc:
                # "Publish the others" (spec 0007, X3): the page is reported as
                # failed and the rest of the site is still published.
                if not exclude_failed:
                    raise
                row.status = "failed"
                row.reason = (getattr(exc, "message", None) or str(exc))[:500]
                row.error_code = (getattr(exc, "code", None) or "processing_failed")[
                    :80
                ]
                row.updated_at = job.updated_at = now()
                released = website_crawl.clear_body(row)
                session.commit()
                website_crawl.finish_release(db_engine, row_id, released)
                continue
            row.source_item_id = source_item.id
            row.source_revision_id = revision.id
            row.classification = classification
            row.extracted_hash = extracted_hash
            row.warnings = website_ingestion.page_warnings(artifact)
            row.updated_at = job.updated_at = now()
            # The revision keeps its own artifact; the crawl copy is no longer needed.
            released = website_crawl.clear_body(row)
            session.commit()
        website_crawl.finish_release(db_engine, row_id, released)
    return True


class _Fenced(Exception):
    """The run was taken over or ended while processing."""


def _crawled_items(db_engine, run_id, execution):
    """Run outcomes from the frontier, in source order then discovery order."""
    order = {
        node.id: position
        for position, node in enumerate(execution.nodes)
        if node.type == "source"
    }
    with Session(db_engine) as session:
        rows = session.scalars(
            select(WebsiteCrawlFrontier).where(WebsiteCrawlFrontier.run_id == run_id)
        ).all()
        session.expunge_all()
    rows.sort(key=lambda row: row.ordinal)
    return [
        (source_node_id, outcome, row)
        for source_node_id in order
        for outcome, row in website_crawl.outcomes_for(
            [row for row in rows if row.source_node_id == source_node_id]
        )
    ]


def _credentialed_priors(session, job, kind):
    index_id = job.snapshot.get("prior_ready_index_id")
    if not index_id:
        return {}
    rows = session.execute(
        select(IndexSourceRevision.source_node_id, SourceItem, SourceRevision)
        .select_from(IndexSourceRevision)
        .join(SourceItem, SourceItem.id == IndexSourceRevision.source_item_id)
        .join(
            SourceRevision, SourceRevision.id == IndexSourceRevision.source_revision_id
        )
        .where(
            IndexSourceRevision.index_id == UUID(index_id),
            IndexSourceRevision.project_id == job.project_id,
            SourceItem.kind == kind,
        )
    ).all()
    return {
        (source_node_id, item.canonical_location): (item, revision)
        for source_node_id, item, revision in rows
    }


def _discover_credentialed(
    run_id,
    token,
    db_engine,
    connector_factory,
    *,
    kind,
    connector_type,
    persistence,
):
    with Session(db_engine) as session:
        job = session.get(IngestionRun, run_id)
        execution = IngestionExecution.model_validate(job.snapshot["execution"])
        priors = _credentialed_priors(session, job, kind)
        keyring = ConnectionKeyring.from_settings(settings)
        chunk = next(node for node in execution.nodes if node.type == "chunk")
        clean = next(node for node in execution.nodes if node.type == "clean")
        extract = next(node for node in execution.nodes if node.type == "extract")
        _, processing_hash = persistence.processing_configuration(chunk, clean, extract)
        sources = [
            (
                source,
                connections.credentials_for_use(
                    session,
                    job.project_id,
                    source.config.connection_id,
                    kind,
                    keyring,
                ),
            )
            for source in execution.nodes
            if source.type == "source"
        ]

    # Never hold a database transaction open during bounded provider calls.
    results = []
    for source, credentials in sources:
        if not ingestion_execution.transition(
            db_engine, run_id, node_id=source.id, execution_token=token
        ):
            return execution, priors, results
        connector = (
            connector_factory(credentials)
            if connector_factory
            else connector_type(credentials)
        )
        if kind == "confluence":

            def cancelled():
                with Session(db_engine) as cancellation_session:
                    current = cancellation_session.get(IngestionRun, run_id)
                    return (
                        current is None
                        or current.status != "running"
                        or current.execution_token != token
                    )

            connector.cancellation_check = cancelled
        source_priors = {
            location: revision
            for (node_id, location), (_, revision) in priors.items()
            if node_id == source.id
        }
        outcomes, artifacts = connector.fetch_all(
            source.config, source_priors, processing_hash
        )
        results.append((source.id, source.config.connection_id, outcomes, artifacts))
    return execution, priors, results


def _advance_credentialed_snapshot(
    run_id,
    token,
    db_engine,
    *,
    kind,
    label,
    persistence,
):
    with Session(db_engine) as session:
        job = session.get(IngestionRun, run_id)
        execution = IngestionExecution.model_validate(job.snapshot["execution"])
    for source in [node for node in execution.nodes if node.type == "source"]:
        if not ingestion_execution.transition(
            db_engine, run_id, node_id=source.id, execution_token=token
        ):
            return
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    clean = next(node for node in execution.nodes if node.type == "clean")
    extract = next(node for node in execution.nodes if node.type == "extract")
    processing_config, processing_hash = persistence.processing_configuration(
        chunk, clean, extract
    )

    def phase_callback(node_type):
        return ingestion_execution.transition(
            db_engine,
            run_id,
            node_type=node_type,
            execution_token=token,
        )

    with Session(db_engine) as session:
        job = session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
        )
        if job.status != "running" or job.execution_token != token:
            return
        if session.scalar(
            select(WebsiteRunItem.run_id)
            .where(WebsiteRunItem.run_id == run_id)
            .limit(1)
        ):
            return
        members = session.execute(
            select(SourceSnapshotMember.source_node_id, SourceItem, SourceRevision)
            .select_from(SourceSnapshotMember)
            .join(SourceItem, SourceItem.id == SourceSnapshotMember.source_item_id)
            .join(
                SourceRevision,
                SourceRevision.id == SourceSnapshotMember.source_revision_id,
            )
            .where(
                SourceSnapshotMember.snapshot_id == job.source_snapshot_id,
                SourceSnapshotMember.project_id == job.project_id,
                SourceItem.kind == kind,
            )
            .order_by(SourceSnapshotMember.ordinal)
        ).all()
        if not members:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="snapshot_members_unavailable",
                    message=f"The selected source snapshot has no reusable {label}s.",
                    retryable=False,
                )
            )
        memberships = []
        for ordinal, (source_node_id, item, revision) in enumerate(members):
            source_run = session.get(ProcessingRun, revision.processing_run_id)
            if source_run is None:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="snapshot_derivation_unavailable",
                        message="A retained source derivation is unavailable for rebuilding.",
                        retryable=False,
                    )
                )
            target_revision = source_artifacts.reprocess_source_revision(
                session,
                job.project_id,
                item,
                revision,
                processing_config=processing_config,
                processing_config_hash=processing_hash,
                parser_version=source_run.parser_version,
                chunk_size=chunk.size,
                chunk_overlap=chunk.overlap,
                chunk_config_version=chunk.config_version,
                reuse_stage=phase_callback,
            )
            classification = (
                "unchanged" if target_revision.id == revision.id else "changed"
            )
            website_ingestion.add_run_item(
                session,
                run=job,
                ordinal=ordinal,
                source_node_id=source_node_id,
                outcome=classification,
                reason=f"Retained {label} artifact reused without a network fetch.",
                location=item.canonical_location,
                display_name=item.external_id,
                media_type=target_revision.media_type,
                source_item=item,
                revision=target_revision,
            )
            memberships.append((source_node_id, item, target_revision))
        job.discovered_count = len(memberships)
        job.processed_count = len(memberships)
        job.failed_count = 0
        ingestion_execution.transition(
            db_engine, run_id, node_type="embed", execution_token=token
        )
        processing_ids = list(
            dict.fromkeys(revision.processing_run_id for _, _, revision in memberships)
        )
        index = indexes.create_index_from_processing_runs(
            session,
            job.project_id,
            job.knowledge_set_id,
            processing_ids,
            ingestion_run_id=job.id,
            source_snapshot_id=job.source_snapshot_id,
            expected_embedding=job.snapshot.get("embedding"),
            commit=False,
        )
        session.execute(
            insert(IndexSourceRevision),
            [
                {
                    "index_id": index.id,
                    "source_revision_id": revision.id,
                    "source_item_id": item.id,
                    "source_node_id": source_node_id,
                    "project_id": job.project_id,
                }
                for source_node_id, item, revision in memberships
            ],
        )
        job.stage = "indexing"
        job.chunk_count = index.chunk_count
        job.progress = 40
        job.status = "queued"
        job.execution_token = None
        job.failures = 0
        job.dispatched_at = None
        job.updated_at = now()
        session.commit()


def _advance_credentialed(
    run_id,
    token,
    db_engine,
    connector_factory,
    *,
    kind,
    label,
    connector_type,
    persistence,
):
    with Session(db_engine) as session:
        job = session.get(IngestionRun, run_id)
        source_input = job.snapshot.get("source_input") or {}
        reuse_stored = bool(job.snapshot.get("reuse_stored"))
    if source_input.get("kind") == "snapshot" or reuse_stored:
        return _advance_credentialed_snapshot(
            run_id,
            token,
            db_engine,
            kind=kind,
            label=label,
            persistence=persistence,
        )
    execution, prior_revisions, results = _discover_credentialed(
        run_id,
        token,
        db_engine,
        connector_factory,
        kind=kind,
        connector_type=connector_type,
        persistence=persistence,
    )
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    clean = next(node for node in execution.nodes if node.type == "clean")
    extract = next(node for node in execution.nodes if node.type == "extract")
    exclude_failed = excludes_failed_items(getattr(extract, "quality_policy", None))

    def phase_callback(node_type):
        return ingestion_execution.transition(
            db_engine,
            run_id,
            node_type=node_type,
            execution_token=token,
        )

    with Session(db_engine) as session:
        job = session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
        )
        if job.status != "running" or job.execution_token != token:
            return
        if session.scalar(
            select(WebsiteRunItem.run_id)
            .where(WebsiteRunItem.run_id == run_id)
            .limit(1)
        ):
            return
        ordinal = 0
        included = set()
        memberships = []
        seen_extracted = {}
        failed = 0
        failed_keys = set()
        for source_node_id, connection_id, outcomes, artifacts in results:
            artifact_by_location = {
                artifact.item.canonical_location: artifact for artifact in artifacts
            }
            for outcome in outcomes:
                if outcome.status != "included":
                    add_outcome = (
                        "failed" if outcome.status == "failed" else outcome.status
                    )
                    website_ingestion.add_run_item(
                        session,
                        run=job,
                        ordinal=ordinal,
                        source_node_id=source_node_id,
                        outcome=add_outcome,
                        reason=outcome.reason,
                        location=outcome.canonical_location,
                        display_name=outcome.display_name,
                        media_type=outcome.media_type,
                        error=outcome.error_code,
                    )
                    if outcome.status == "failed":
                        failed += 1
                        failed_keys.add((source_node_id, outcome.canonical_location))
                    ordinal += 1
                    continue
                artifact = artifact_by_location[outcome.canonical_location]
                prior_entry = prior_revisions.get(
                    (source_node_id, artifact.item.canonical_location)
                )
                prior_item, prior = prior_entry if prior_entry else (None, None)
                if artifact.unchanged:
                    if prior is None or prior_item is None:
                        raise ConnectorFailure(
                            ConnectorIssue(
                                code="prior_revision_unavailable",
                                message=f"A prior {label} revision is unavailable for safe refresh.",
                                retryable=True,
                            )
                        )
                    source_item, revision = prior_item, prior
                    classification = "unchanged"
                    extracted_hash = revision.extracted_hash
                else:
                    try:
                        # A savepoint keeps a failed item's partial rows out of the run.
                        with session.begin_nested():
                            (
                                source_item,
                                revision,
                                classification,
                                extracted_hash,
                                _stored_path,
                            ) = persistence.persist_artifact(
                                session,
                                job.project_id,
                                connection_id,
                                artifact,
                                chunk,
                                clean,
                                prior,
                                phase_callback,
                                extract,
                            )
                    except (ProcessingError, IngestionStageError) as exc:
                        # "Publish the others" (spec 0007, X3): record and skip it.
                        if not exclude_failed:
                            raise
                        website_ingestion.add_run_item(
                            session,
                            run=job,
                            ordinal=ordinal,
                            source_node_id=source_node_id,
                            outcome="failed",
                            reason=getattr(exc, "message", None) or str(exc),
                            location=outcome.canonical_location,
                            display_name=outcome.display_name,
                            media_type=outcome.media_type,
                            error=getattr(exc, "code", None) or "processing_failed",
                        )
                        failed += 1
                        failed_keys.add((source_node_id, outcome.canonical_location))
                        ordinal += 1
                        continue
                if (
                    getattr(clean, "duplicate_policy", None) is None
                    and clean.exact_content_deduplication
                    and extracted_hash in seen_extracted
                ):
                    classification = "excluded"
                    reason = f"Extracted text duplicates another included {label}."
                    duplicate_decision = {
                        "outcome": "excluded",
                        "retained_identity": seen_extracted[extracted_hash],
                        "excluded_identity": artifact.item.canonical_location,
                        "method": "exact_cleaned_sha256",
                        "similarity": 1.0,
                        "reason": "Excluded in favor of the deterministic canonical source.",
                    }
                else:
                    seen_extracted[extracted_hash] = artifact.item.canonical_location
                    included.add((source_node_id, artifact.item.canonical_location))
                    memberships.append((source_node_id, source_item, revision))
                    reason = f"{label.capitalize()} revision is {classification}."
                    duplicate_decision = {
                        "outcome": "retained",
                        "retained_identity": artifact.item.canonical_location,
                        "excluded_identity": None,
                        "method": "unique",
                        "similarity": 1.0,
                        "reason": "No duplicate matched the saved policy.",
                    }
                website_ingestion.add_run_item(
                    session,
                    run=job,
                    ordinal=ordinal,
                    source_node_id=source_node_id,
                    outcome=classification,
                    reason=reason,
                    location=artifact.item.canonical_location,
                    display_name=artifact.item.display_name,
                    media_type=artifact.item.media_type,
                    source_item=source_item,
                    revision=revision,
                    duplicate_decision=duplicate_decision,
                )
                ordinal += 1
        memberships = _apply_duplicate_policy(session, job.id, memberships, clean, kind)
        for key, (item, revision) in prior_revisions.items():
            # A page that failed to fetch is reported as failed, not as removed.
            if key in included or key in failed_keys:
                continue
            source_node_id, location = key
            website_ingestion.add_run_item(
                session,
                run=job,
                ordinal=ordinal,
                source_node_id=source_node_id,
                outcome="removed",
                reason=f"Previously indexed {label} was not included by this refresh.",
                location=location,
                display_name=item.external_id,
                source_item=item,
                revision=revision,
                media_type=revision.media_type,
            )
            ordinal += 1
        job.discovered_count = ordinal
        job.failed_count = failed
        job.processed_count = ordinal - failed
        if failed and (not exclude_failed or not memberships):
            fail_run(
                session,
                job,
                (
                    f"No {label} could be included. The previous ready index remains current."
                    if exclude_failed
                    else f"One or more required {label}s failed. The previous ready index "
                    "remains current."
                ),
                node_type="source",
            )
            session.commit()
            return
        if not memberships:
            raise HTTPException(
                409, f"{label.capitalize()} discovery found no indexable pages."
            )
        ingestion_execution.transition(
            db_engine, run_id, node_type="embed", execution_token=token
        )
        if (
            job.source_snapshot_id is not None
            and (job.snapshot.get("source_input") or {}).get("kind") == "refresh"
        ):
            source_snapshots.mark_ready(session, job.source_snapshot_id, memberships)
        processing_ids = list(
            dict.fromkeys(revision.processing_run_id for _, _, revision in memberships)
        )
        index = indexes.create_index_from_processing_runs(
            session,
            job.project_id,
            job.knowledge_set_id,
            processing_ids,
            ingestion_run_id=job.id,
            source_snapshot_id=job.source_snapshot_id,
            expected_embedding=job.snapshot.get("embedding"),
            commit=False,
        )
        session.execute(
            insert(IndexSourceRevision),
            [
                {
                    "index_id": index.id,
                    "source_revision_id": revision.id,
                    "source_item_id": item.id,
                    "source_node_id": source_node_id,
                    "project_id": job.project_id,
                }
                for source_node_id, item, revision in memberships
            ],
        )
        job.stage = "indexing"
        job.chunk_count = index.chunk_count
        job.progress = 40
        job.status = "queued"
        job.execution_token = None
        job.failures = 0
        job.dispatched_at = None
        job.updated_at = now()
        session.commit()


def _advance_s3(run_id, token, db_engine, connector_factory):
    return _advance_credentialed(
        run_id,
        token,
        db_engine,
        connector_factory,
        kind="s3",
        label="S3 object",
        connector_type=S3Connector,
        persistence=s3_ingestion,
    )


def _advance_notion(run_id, token, db_engine, connector_factory):
    return _advance_credentialed(
        run_id,
        token,
        db_engine,
        connector_factory,
        kind="notion",
        label="Notion page",
        connector_type=NotionConnector,
        persistence=notion_ingestion,
    )


def _advance_confluence(run_id, token, db_engine, connector_factory):
    return _advance_credentialed(
        run_id,
        token,
        db_engine,
        connector_factory,
        kind="confluence",
        label="Confluence page",
        connector_type=ConfluenceConnector,
        persistence=confluence_ingestion,
    )


def _advance_website(run_id, token, db_engine, connector_factory):
    execution, prior_revisions, results = _discover_website(
        run_id, token, db_engine, connector_factory
    )
    if results is None:
        return
    crawled = results is CRAWLED
    if crawled:
        if not _process_crawled(run_id, token, db_engine, execution, prior_revisions):
            return
        items = _crawled_items(db_engine, run_id, execution)
        results = []
    else:
        items = []
        for source_node_id, outcomes, artifacts in results:
            artifact_by_location = {
                artifact.canonical_location: artifact for artifact in artifacts
            }
            items.extend(
                (
                    source_node_id,
                    outcome,
                    artifact_by_location[outcome.canonical_location]
                    if outcome.status == "included"
                    else None,
                )
                for outcome in outcomes
            )
    chunk = next(node for node in execution.nodes if node.type == "chunk")
    clean = next(node for node in execution.nodes if node.type == "clean")
    extract = next(node for node in execution.nodes if node.type == "extract")
    # Keyed by (source node, location): two sources may reach the same URL.
    extracted_by_location = {}
    # Repeated site chrome is measured per source, never across sites.
    repeated_site_fingerprints = {}
    if getattr(clean, "profile", None) == "structure-aware-v1":
        from app.ingestion_content.cleaning import website_text_fingerprints

        main_step = next(
            (
                step
                for step in clean.steps
                if step.enabled and step.type == "website_main_content"
            ),
            None,
        )
        for source_node_id, outcomes, artifacts in results:
            included = {
                outcome.canonical_location
                for outcome in outcomes
                if outcome.status == "included"
            }
            source_documents = []
            for artifact in artifacts:
                if artifact.canonical_location in included:
                    document = website_ingestion.canonical_extracted_document(
                        artifact, clean, extract
                    )
                    extracted_by_location[
                        (source_node_id, artifact.canonical_location)
                    ] = document
                    source_documents.append(document)
            if main_step is not None and main_step.remove_repeated_site_chrome:
                repeated_site_fingerprints[source_node_id] = website_text_fingerprints(
                    source_documents, main_step.minimum_page_ratio
                )

    def phase_callback(node_type):
        return ingestion_execution.transition(
            db_engine,
            run_id,
            node_type=node_type,
            execution_token=token,
        )

    with Session(db_engine) as session:
        job = session.scalar(
            select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
        )
        if job.status != "running" or job.execution_token != token:
            return
        if session.scalar(
            select(WebsiteRunItem.run_id)
            .where(WebsiteRunItem.run_id == run_id)
            .limit(1)
        ):
            return
        ordinal = 0
        included_locations = set()
        memberships = []
        seen_extracted = {}
        failed = 0
        failed_locations = set()
        # Source item id -> (source node, location) of the copy that is indexed.
        kept_items = {}
        # Source item id -> other places the indexed page was also found.
        also_found = {}
        sources = [node for node in execution.nodes if node.type == "source"]
        # With several crawled sources, one failing site does not block the
        # others: its last good pages are carried forward instead.
        isolate = crawled and len(sources) > 1
        failed_sources = (
            dict(_failed_sources(job.crawl_state, execution)) if isolate else {}
        )
        refresh_only = _refresh_only(job)
        skipped_sources = {
            source.id
            for source in sources
            if refresh_only is not None and source.id not in refresh_only
        }
        included_by_source = Counter()
        failed_by_source = Counter()
        for source_node_id, outcome, resolved in items:
            if source_node_id in failed_sources:
                continue
            if outcome.status != "included":
                add_outcome = "failed" if outcome.status == "failed" else outcome.status
                website_ingestion.add_run_item(
                    session,
                    run=job,
                    ordinal=ordinal,
                    source_node_id=source_node_id,
                    outcome=add_outcome,
                    reason=outcome.reason,
                    location=outcome.canonical_location,
                    display_name=outcome.display_name,
                    media_type=outcome.media_type,
                    error=outcome.error_code,
                    attempts=outcome.attempts,
                )
                if outcome.status == "failed":
                    failed += 1
                    failed_by_source[source_node_id] += 1
                    failed_locations.add(outcome.canonical_location)
                ordinal += 1
                continue
            included_by_source[source_node_id] += 1
            if isinstance(resolved, WebsiteCrawlFrontier):
                # Processed page by page already; the frontier holds the result.
                source_item = session.get(SourceItem, resolved.source_item_id)
                revision = session.get(SourceRevision, resolved.source_revision_id)
                classification = resolved.classification
                extracted_hash = resolved.extracted_hash
                location = resolved.final_url
                media_type = resolved.media_type
                warnings = resolved.warnings
            else:
                artifact = resolved
                location = artifact.canonical_location
                media_type = artifact.media_type
                warnings = website_ingestion.page_warnings(artifact)
                prior_entry = prior_revisions.get(location)
                prior = prior_entry[0] if prior_entry else None
                try:
                    with session.begin_nested():
                        (
                            source_item,
                            revision,
                            classification,
                            extracted_hash,
                            _stored_path,
                        ) = website_ingestion.persist_artifact(
                            session,
                            job.project_id,
                            artifact,
                            chunk,
                            clean,
                            prior,
                            phase_callback,
                            extract,
                            extracted_by_location.get((source_node_id, location)),
                            repeated_site_fingerprints.get(source_node_id, set()),
                        )
                except (ProcessingError, IngestionStageError) as exc:
                    # "Publish the others" (spec 0007, X3).
                    if not excludes_failed_items(
                        getattr(extract, "quality_policy", None)
                    ):
                        raise
                    included_by_source[source_node_id] -= 1
                    website_ingestion.add_run_item(
                        session,
                        run=job,
                        ordinal=ordinal,
                        source_node_id=source_node_id,
                        outcome="failed",
                        reason=getattr(exc, "message", None) or str(exc),
                        location=location,
                        display_name=outcome.display_name,
                        media_type=media_type,
                        error=getattr(exc, "code", None) or "processing_failed",
                    )
                    failed += 1
                    failed_by_source[source_node_id] += 1
                    failed_locations.add(location)
                    ordinal += 1
                    continue
            kept = kept_items.get(source_item.id)
            if kept is not None:
                # Another source already reached this exact page. An index holds
                # one revision per source item, so it is indexed once and the
                # kept page records this source as well.
                kept_node_id, kept_location = kept
                also_found.setdefault(source_item.id, []).append(
                    {
                        "source_node_id": source_node_id,
                        "canonical_location": location,
                        "reason": "same_page",
                    }
                )
                website_ingestion.add_run_item(
                    session,
                    run=job,
                    ordinal=ordinal,
                    source_node_id=source_node_id,
                    outcome="duplicate",
                    reason=(
                        f"Same page as {kept_location}, already included by "
                        f"source {kept_node_id}; indexed once."
                    ),
                    location=location,
                    display_name=outcome.display_name,
                    media_type=media_type,
                    source_item=source_item,
                    revision=revision,
                    duplicate_decision={
                        "outcome": "excluded",
                        "retained_identity": kept_location,
                        "excluded_identity": location,
                        "method": "same_source_item",
                        "similarity": 1.0,
                        "reason": "Another source in this run reached the same page.",
                    },
                    attempts=outcome.attempts,
                    warnings=warnings,
                )
                ordinal += 1
                continue
            kept_items[source_item.id] = (source_node_id, location)
            if (
                getattr(clean, "duplicate_policy", None) is None
                and clean.exact_content_deduplication
                and extracted_hash in seen_extracted
            ):
                retained_location, retained_item_id = seen_extracted[extracted_hash]
                also_found.setdefault(retained_item_id, []).append(
                    {
                        "source_node_id": source_node_id,
                        "canonical_location": location,
                        "reason": "exact_cleaned_sha256",
                    }
                )
                classification = "excluded"
                reason = "Extracted text duplicates another included website page."
                duplicate_decision = {
                    "outcome": "excluded",
                    "retained_identity": retained_location,
                    "excluded_identity": location,
                    "method": "exact_cleaned_sha256",
                    "similarity": 1.0,
                    "reason": "Excluded in favor of the deterministic canonical source.",
                }
            else:
                seen_extracted[extracted_hash] = (location, source_item.id)
                included_locations.add(location)
                memberships.append((source_node_id, source_item, revision))
                reason = f"Website revision is {classification}."
                duplicate_decision = {
                    "outcome": "retained",
                    "retained_identity": location,
                    "excluded_identity": None,
                    "method": "unique",
                    "similarity": 1.0,
                    "reason": "No duplicate matched the saved policy.",
                }
            website_ingestion.add_run_item(
                session,
                run=job,
                ordinal=ordinal,
                source_node_id=source_node_id,
                outcome=classification,
                reason=reason,
                location=location,
                display_name=outcome.display_name,
                media_type=media_type,
                source_item=source_item,
                revision=revision,
                duplicate_decision=duplicate_decision,
                attempts=outcome.attempts,
                warnings=warnings,
            )
            ordinal += 1
        carried = []
        if isolate:
            for source in sources:
                # A source whose every page failed is treated as a failed site.
                if (
                    source.id not in failed_sources
                    and failed_by_source[source.id]
                    and not included_by_source[source.id]
                ):
                    failed_sources[source.id] = {
                        "code": "all_pages_failed",
                        "message": "Every page of this source failed; see its failed items.",
                    }
            refreshed = [
                source for source in sources if source.id not in skipped_sources
            ]
            if all(source.id in failed_sources for source in refreshed):
                job.discovered_count = ordinal
                job.failed_count = failed
                job.processed_count = ordinal - failed
                job.crawl_state = {
                    **(job.crawl_state or {}),
                    OUTCOMES_STATE: _source_outcomes(
                        sources,
                        failed_sources,
                        included_by_source,
                        failed_by_source,
                        Counter(),
                        skipped_sources,
                    ),
                }
                fail_run(
                    session,
                    job,
                    (
                        "Every refreshed Website source failed."
                        if skipped_sources
                        else "Every Website source failed."
                    )
                    + " The previous ready index remains current.",
                    node_type="source",
                )
                session.commit()
                return
            for location, (revision, prior_source_node_id) in prior_revisions.items():
                if location in included_locations:
                    continue
                if prior_source_node_id in skipped_sources:
                    reason = (
                        "Kept from the previous index; this source was not "
                        "refreshed in this run."
                    )
                elif prior_source_node_id in failed_sources:
                    reason = (
                        "Kept from the previous index because this source failed: "
                        + failed_sources[prior_source_node_id]["message"]
                    )
                elif location in failed_locations:
                    reason = (
                        "Kept the previously indexed copy because this page failed."
                    )
                else:
                    continue
                carried.append((location, revision, prior_source_node_id, reason))
        carried_by_source = Counter()
        carried_locations = set()
        for membership, location, reason in _carry_forward(
            session, job, carried, kept_items, chunk, clean, extract, phase_callback
        ):
            source_node_id, item, revision = membership
            memberships.append(membership)
            carried_locations.add(location)
            carried_by_source[source_node_id] += 1
            website_ingestion.add_run_item(
                session,
                run=job,
                ordinal=ordinal,
                source_node_id=source_node_id,
                outcome="carried_forward",
                reason=reason,
                location=location,
                source_item=item,
                revision=revision,
                media_type=revision.media_type,
            )
            ordinal += 1
        memberships = _apply_duplicate_policy(
            session, job.id, memberships, clean, "website", also_found
        )
        for location, (revision, prior_source_node_id) in prior_revisions.items():
            # A page that failed to fetch is reported as failed, not as removed;
            # a failed source's pages are kept, never removed.
            if (
                location in included_locations
                or location in failed_locations
                or location in carried_locations
                or prior_source_node_id in failed_sources
                or prior_source_node_id in skipped_sources
            ):
                continue
            item = session.get(SourceItem, revision.source_item_id)
            website_ingestion.add_run_item(
                session,
                run=job,
                ordinal=ordinal,
                source_node_id=prior_source_node_id,
                outcome="removed",
                reason="Previously indexed URL was not included by this refresh.",
                location=location,
                source_item=item,
                revision=revision,
                media_type=revision.media_type,
            )
            ordinal += 1
        job.discovered_count = ordinal
        job.failed_count = failed
        job.processed_count = ordinal - failed
        if isolate:
            job.crawl_state = {
                **(job.crawl_state or {}),
                OUTCOMES_STATE: _source_outcomes(
                    sources,
                    failed_sources,
                    included_by_source,
                    failed_by_source,
                    carried_by_source,
                    skipped_sources,
                ),
            }
        elif failed and not excludes_failed_items(
            getattr(extract, "quality_policy", None)
        ):
            fail_run(
                session,
                job,
                "One or more required website pages failed. The previous ready index remains current.",
                node_type="source",
            )
            session.commit()
            return
        if (isolate or failed) and not memberships:
            fail_run(
                session,
                job,
                "No Website page could be included. The previous ready index remains current.",
                node_type="source",
            )
            session.commit()
            return
        website_ingestion.require_artifacts(memberships)
        ingestion_execution.transition(
            db_engine, run_id, node_type="embed", execution_token=token
        )
        if (
            job.source_snapshot_id is not None
            and (job.snapshot.get("source_input") or {}).get("kind") == "refresh"
        ):
            source_snapshots.mark_ready(
                session, job.source_snapshot_id, memberships, also_found
            )
        processing_ids = list(
            dict.fromkeys(revision.processing_run_id for _, _, revision in memberships)
        )
        index = indexes.create_index_from_processing_runs(
            session,
            job.project_id,
            job.knowledge_set_id,
            processing_ids,
            ingestion_run_id=job.id,
            source_snapshot_id=job.source_snapshot_id,
            expected_embedding=job.snapshot.get("embedding"),
            commit=False,
        )
        session.execute(
            insert(IndexSourceRevision),
            [
                {
                    "index_id": index.id,
                    "source_revision_id": revision.id,
                    "source_item_id": item.id,
                    "source_node_id": source_node_id,
                    "project_id": job.project_id,
                }
                for source_node_id, item, revision in memberships
            ],
        )
        job.stage = "indexing"
        job.chunk_count = index.chunk_count
        job.progress = 40
        job.status = "queued"
        job.execution_token = None
        job.failures = 0
        job.dispatched_at = None
        job.updated_at = now()
        session.commit()


def _source_location(config):
    selection = config.selection
    if selection.mode == "url_list":
        return str(selection.urls[0]) if selection.urls else None
    if selection.mode == "single_url":
        return str(selection.url)
    if selection.mode == "crawl":
        return str(selection.start_url)
    return str(selection.sitemap_url)


def _source_outcomes(sources, failed, included, page_failures, carried, skipped=()):
    """Per-source result of a multi-source run, shown with the run."""
    outcomes = []
    for source in sources:
        failure = failed.get(source.id)
        if source.id in skipped:
            status = "skipped"
        elif failure:
            status = "failed"
        elif page_failures[source.id]:
            status = "partial"
        else:
            status = "succeeded"
        outcomes.append(
            {
                "source_node_id": source.id,
                "location": _source_location(source.config),
                "status": status,
                "error_code": failure["code"] if failure else None,
                "message": failure["message"] if failure else None,
                "included_count": included[source.id],
                "failed_count": page_failures[source.id],
                "carried_forward_count": carried[source.id],
            }
        )
    return outcomes


def _stored_page(session, location, revision):
    document = session.get(Document, revision.document_id)
    try:
        if document is None:
            raise FileNotFoundError
        content = artifact_storage.read(document)
    except OSError as exc:
        raise ConnectorFailure(
            ConnectorIssue(
                code="prior_artifact_unavailable",
                message="A previously indexed page is unavailable for reprocessing.",
                retryable=False,
            )
        ) from exc
    return WebsiteArtifact(
        canonical_location=location,
        content=content,
        media_type=revision.media_type,
        etag=revision.etag,
        last_modified=revision.last_modified,
        validator_unchanged=True,
        depth=(revision.provenance or {}).get("depth") or 0,
    )


def _carry_forward(session, job, carried, kept_items, chunk, clean, extract, stage):
    """Memberships for carried pages, reprocessed if the processing settings changed.

    Yields ((source node, item, revision), location, reason). A page already
    indexed from another source in this run is skipped.
    """
    if not carried:
        return
    _, current_hash, _ = website_ingestion.website_processing_identity(
        chunk, clean, extract
    )
    stale = {}
    for location, revision, source_node_id, reason in carried:
        if revision.source_item_id in kept_items:
            continue
        if revision.processing_config_hash == current_hash:
            item = session.get(SourceItem, revision.source_item_id)
            kept_items[item.id] = (source_node_id, location)
            yield (source_node_id, item, revision), location, reason
        else:
            stale.setdefault(source_node_id, []).append((location, revision, reason))
    main_step = next(
        (
            step
            for step in getattr(clean, "steps", None) or []
            if step.enabled and step.type == "website_main_content"
        ),
        None,
    )
    for source_node_id, pages in stale.items():
        # Stored pages are cleaned again with this run's settings, without a
        # request to the site; chrome is measured across this source's pages.
        fingerprints = set()
        if (
            getattr(clean, "profile", None) == "structure-aware-v1"
            and main_step is not None
            and main_step.remove_repeated_site_chrome
        ):
            from app.ingestion_content.cleaning import website_text_fingerprints

            fingerprints = website_text_fingerprints(
                (
                    website_ingestion.canonical_extracted_document(
                        _stored_page(session, location, revision), clean, extract
                    )
                    for location, revision, _ in pages
                ),
                main_step.minimum_page_ratio,
            )
        for location, revision, reason in pages:
            item, new_revision, _, _, _ = website_ingestion.persist_artifact(
                session,
                job.project_id,
                _stored_page(session, location, revision),
                chunk,
                clean,
                revision,
                stage,
                extract,
                None,
                fingerprints,
            )
            if item.id in kept_items:
                continue
            kept_items[item.id] = (source_node_id, location)
            yield (
                (source_node_id, item, new_revision),
                location,
                reason + " Reprocessed with this run's settings.",
            )


def finish_remote(session, job, index):
    items = session.scalars(
        select(WebsiteRunItem).where(WebsiteRunItem.run_id == job.id)
    ).all()
    # A multi-source run can publish with failed pages; they stay failed.
    failed = 0
    for item in items:
        if item.outcome == "failed":
            failed += 1
            continue
        if item.status == "skipped":
            continue
        item.status = "succeeded"
        item.updated_at = now()
    job.status = "succeeded"
    job.stage = "complete"
    job.progress = 100
    job.processed_count = job.discovered_count - failed
    job.failed_count = failed
    job.chunk_count = index.chunk_count
    job.embedded_count = index.embedded_count
    job.published_count = 1
    job.execution_token = None
    job.failures = 0
    job.error = None
    job.updated_at = job.finished_at = now()
    ingestion_execution.mark_terminal(session, job.id, "succeeded")


_REMOTE_ADVANCERS = {
    "website": _advance_website,
    "s3": _advance_s3,
    "notion": _advance_notion,
    "confluence": _advance_confluence,
}


def advance_remote(kind, run_id, token, db_engine, connector_factory=None):
    """Advance one supported remote connector without weakening its own semantics."""
    try:
        advance = _REMOTE_ADVANCERS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported remote ingestion source: {kind}") from exc
    return advance(run_id, token, db_engine, connector_factory)
