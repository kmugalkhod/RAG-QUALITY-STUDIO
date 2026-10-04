"""Persistent, fenced Website crawl frontier for ingestion runs.

The connector decides scope and fetches pages; this store records each decision
in `website_crawl_frontier` in one transaction per page, after checking the run's
execution token, so a recovered run resumes from its last page instead of
refetching every page. Raw page bodies are stored encrypted like documents and
released once the run ends.
"""

from __future__ import annotations

import logging
from collections import deque
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.connectors.website import (
    CrawlAdmission,
    CrawlEntry,
    CrawlProgress,
    CrawlResume,
    PageResult,
    PreviewOutcome,
    WebsiteArtifact,
    _move_to_front,
    duplicate_outcome,
    record_state,
)
from app.core.config import settings
from app.models.ingestion import IngestionRun
from app.models.source import WebsiteCrawlFrontier
from app.services import artifact_storage

TERMINAL_RUN_STATUSES = ("succeeded", "failed", "cancelled")


def now() -> datetime:
    return datetime.now(timezone.utc)


def _worker_engine(db_engine):
    return db_engine.execution_options(isolation_level="READ COMMITTED")


def _locked_run(session: Session, run_id: UUID, token: UUID) -> IngestionRun | None:
    run = session.scalar(
        select(IngestionRun).where(IngestionRun.id == run_id).with_for_update()
    )
    if run is None or run.status != "running" or run.execution_token != token:
        return None
    return run


class RunCrawlStore:
    """Crawl state of one Website source node in one ingestion run."""

    def __init__(self, db_engine, run_id: UUID, token: UUID, source_node_id: str):
        self.engine = _worker_engine(db_engine)
        self.run_id = run_id
        self.token = token
        self.node = source_node_id
        with Session(self.engine) as session:
            run = session.get(IngestionRun, run_id)
            self.project_id = run.project_id
            self.max_pages = (
                (run.snapshot.get("fetch_policies") or {})
                .get(source_node_id, {})
                .get("max_pages", 1)
            )
            self.state = dict((run.crawl_state or {}).get(source_node_id) or {})
            rows = session.execute(
                select(
                    WebsiteCrawlFrontier.id,
                    WebsiteCrawlFrontier.ordinal,
                    WebsiteCrawlFrontier.canonical_url,
                    WebsiteCrawlFrontier.depth,
                    WebsiteCrawlFrontier.lastmod,
                    WebsiteCrawlFrontier.status,
                    WebsiteCrawlFrontier.seen_again,
                    WebsiteCrawlFrontier.original_url,
                    WebsiteCrawlFrontier.final_url,
                    WebsiteCrawlFrontier.content_hash,
                )
                .where(
                    WebsiteCrawlFrontier.run_id == run_id,
                    WebsiteCrawlFrontier.source_node_id == source_node_id,
                )
                .order_by(WebsiteCrawlFrontier.ordinal)
            ).all()
        self._known = {row.canonical_url for row in rows if row.canonical_url}
        self._pages = sum(
            1 for row in rows if row.canonical_url and row.status != "sitemap"
        )
        self._duplicates = {row.canonical_url for row in rows if row.seen_again}
        self._queue = deque(
            CrawlEntry(
                row.canonical_url,
                row.depth or 0,
                row.lastmod,
                row.id,
                original=row.original_url,
            )
            for row in rows
            if row.status == "queued"
        )
        self._content = {
            row.content_hash: row.final_url
            for row in rows
            if row.status == "fetched" and row.content_hash
        }
        self._fetched = sum(1 for row in rows if row.status == "fetched")
        self._ordinal = max((row.ordinal for row in rows), default=-1)
        self._states: dict[str, str] = {}
        for row in rows:
            if row.canonical_url:
                self._states[row.canonical_url] = row.status
            if row.final_url and row.status != "queued":
                self._states.setdefault(row.final_url, row.status)
        # Page files written in the current transaction, removed if it fails.
        self._written: list[str] = []

    def url_state(self, url: str) -> str | None:
        return self._states.get(url)

    # Discovery bookkeeping, mirrored in memory for the connector's decisions.

    def resume(self) -> CrawlResume:
        return CrawlResume(
            seeded=bool(self.state.get("seeded")),
            transferred=int(self.state.get("transferred_bytes", 0)),
            elapsed_seconds=self.state.get("elapsed_ms", 0) / 1000,
            fetched_pages=self._fetched,
        )

    def count(self) -> int:
        return self._pages

    def omitted(self) -> bool:
        return bool(self.state.get("omitted"))

    def mark_omitted(self) -> None:
        self.state["omitted"] = True

    def is_known(self, url: str) -> bool:
        return url in self._known

    def reserve(self, url: str, *, sitemap: bool = False) -> None:
        self._known.add(url)
        self._pages += not sitemap

    def mark_duplicate(self, url: str) -> bool:
        if url in self._duplicates:
            return False
        self._duplicates.add(url)
        return True

    def content_owner(self, content_hash: str) -> str | None:
        return self._content.get(content_hash)

    def next_queued(self) -> CrawlEntry | None:
        return self._queue.popleft() if self._queue else None

    def has_queued(self) -> bool:
        return bool(self._queue)

    def drain_queued(self) -> list[CrawlEntry]:
        entries = list(self._queue)
        self._queue.clear()
        return entries

    def prioritize(self, url: str) -> None:
        """Fetch a queued URL next; the order on disk is unchanged."""
        _move_to_front(self._queue, url)

    # Fenced writes.

    def _row(self, outcome: PreviewOutcome, *, key=None, lastmod=None):
        self._ordinal += 1
        return WebsiteCrawlFrontier(
            id=uuid4(),
            run_id=self.run_id,
            project_id=self.project_id,
            source_node_id=self.node,
            ordinal=self._ordinal,
            canonical_url=key,
            depth=outcome.depth,
            lastmod=lastmod,
            status=outcome.status,
            attempts=outcome.attempts,
            reason=(outcome.reason or "")[:500],
            error_code=outcome.error_code,
            media_type=outcome.media_type,
            size_bytes=outcome.size_bytes,
            final_url=outcome.canonical_location,
        )

    def _complete(self, session, row, result: PageResult):
        outcome = result.outcome
        row.status = "fetched" if outcome.status == "included" else outcome.status
        row.final_url = outcome.canonical_location
        row.reason = (outcome.reason or "")[:500]
        row.error_code = outcome.error_code
        row.media_type = outcome.media_type
        row.size_bytes = outcome.size_bytes
        row.attempts = outcome.attempts
        row.updated_at = now()
        artifact = result.artifact
        if artifact is not None:
            # An unchanged page (304 or sitemap lastmod) is read again from its
            # prior revision when processed, so its body is not stored twice.
            # The prior is keyed by the queued URL; after a redirect the final
            # URL differs, so the body is stored to keep processing self-contained.
            if not (
                artifact.validator_unchanged
                and artifact.canonical_location == row.canonical_url
            ):
                stored = artifact_storage.store(
                    artifact.content, self.project_id, row.id
                )
                self._written.append(stored.storage_name)
                values = artifact_storage.model_values(stored)
                row.storage_name = values["storage_name"]
                row.artifact_state = values["artifact_state"]
                row.artifact_encryption_schema = values["artifact_encryption_schema"]
                row.artifact_key_version = values["artifact_key_version"]
                row.artifact_wrapped_key = values["artifact_wrapped_key"]
                row.artifact_wrap_nonce = values["artifact_wrap_nonce"]
                row.artifact_content_nonce = values["artifact_content_nonce"]
            row.etag = artifact.etag
            row.last_modified = artifact.last_modified
            row.validator_unchanged = artifact.validator_unchanged
            row.final_url = artifact.canonical_location
            row.content_hash = result.content_hash
            if result.content_hash:
                self._content[result.content_hash] = artifact.canonical_location
            self._fetched += 1

    def commit(
        self,
        completion: tuple[CrawlEntry, PageResult] | None,
        admissions: list[CrawlAdmission],
        progress: CrawlProgress,
        *,
        seeded: bool = False,
        reinstate: bool = False,
    ) -> bool:
        """Record one page and its discoveries in one fenced transaction.

        `reinstate` re-records a page marked duplicate of a canonical target
        that was never indexed, now with its body.
        """
        queued = []
        states = {}
        with Session(self.engine) as session, self._cleanup_on_failure():
            run = _locked_run(session, self.run_id, self.token)
            if run is None:
                return False
            if completion is not None:
                entry, result = completion
                row = session.get(WebsiteCrawlFrontier, entry.key)
                if row is not None and (
                    row.status == "queued" or (reinstate and row.status == "duplicate")
                ):
                    self._complete(session, row, result)
                    record_state(states, entry.url, result)
            for admission in admissions:
                if admission.entry is not None:
                    entry = admission.entry
                    row = self._row(
                        PreviewOutcome(
                            external_id=entry.url,
                            display_name=entry.url,
                            canonical_location=None,
                            media_type=None,
                            status="queued",
                            reason="Queued for fetching.",
                            depth=entry.depth,
                        ),
                        key=entry.url,
                        lastmod=entry.lastmod,
                    )
                    row.original_url = entry.original
                    session.add(row)
                    queued.append((replace(entry, key=row.id), admission.priority))
                    states[entry.url] = "queued"
                elif admission.outcome is not None:
                    session.add(self._row(admission.outcome, key=admission.key))
                    if admission.key:
                        states[admission.key] = admission.outcome.status
            session.flush()
            for admission in admissions:
                if admission.duplicate_of is None:
                    continue
                session.execute(
                    update(WebsiteCrawlFrontier)
                    .where(
                        WebsiteCrawlFrontier.run_id == self.run_id,
                        WebsiteCrawlFrontier.source_node_id == self.node,
                        WebsiteCrawlFrontier.canonical_url == admission.duplicate_of,
                    )
                    .values(
                        seen_again=True,
                        duplicate_url=admission.original or admission.duplicate_of,
                    )
                )
            if seeded:
                self.state["seeded"] = True
            self.state["transferred_bytes"] = progress.transferred
            self.state["elapsed_ms"] = int(progress.elapsed_seconds * 1000)
            self._save_progress(session, run)
            session.commit()
        for entry, priority in queued:
            # A recovered run reloads the queue in discovery order; only the
            # page limit is affected, and a canonical target is rarely last.
            if priority:
                self._queue.appendleft(entry)
            else:
                self._queue.append(entry)
        self._states.update(states)
        return True

    @contextmanager
    def _cleanup_on_failure(self):
        """Delete page files of a transaction that did not commit."""
        self._written = []
        try:
            yield
        except BaseException:
            for name in self._written:
                delete_body(name)
            raise
        finally:
            self._written = []

    def import_results(self, outcomes, artifacts: list[WebsiteArtifact]) -> bool:
        """Record a discovery that already finished elsewhere, in one commit."""
        by_location = {artifact.canonical_location: artifact for artifact in artifacts}
        with Session(self.engine) as session, self._cleanup_on_failure():
            run = _locked_run(session, self.run_id, self.token)
            if run is None:
                return False
            for outcome in outcomes:
                url = outcome.canonical_location
                if outcome.status == "duplicate" and url in self._known:
                    self._duplicates.add(url)
                    session.flush()
                    session.execute(
                        update(WebsiteCrawlFrontier)
                        .where(
                            WebsiteCrawlFrontier.run_id == self.run_id,
                            WebsiteCrawlFrontier.source_node_id == self.node,
                            WebsiteCrawlFrontier.canonical_url == url,
                        )
                        .values(seen_again=True)
                    )
                    continue
                key = url if url and url not in self._known else None
                if key:
                    self._known.add(key)
                row = self._row(outcome, key=key)
                row.status = "queued"
                session.add(row)
                session.flush()
                self._complete(
                    session,
                    row,
                    PageResult(
                        outcome,
                        by_location.get(url) if outcome.status == "included" else None,
                    ),
                )
            self.state["seeded"] = True
            self._save_progress(session, run)
            session.commit()
        return True

    def _save_progress(self, session, run):
        crawl_state = dict(run.crawl_state or {})
        crawl_state[self.node] = dict(self.state)
        run.crawl_state = crawl_state
        counts = dict(
            session.execute(
                select(WebsiteCrawlFrontier.status, func.count())
                .where(WebsiteCrawlFrontier.run_id == self.run_id)
                .group_by(WebsiteCrawlFrontier.status)
            ).all()
        )
        total = min(sum(counts.values()), 50_000)
        run.discovered_count = total
        run.processed_count = min(total - counts.get("queued", 0), total)
        # Discovery is the first third of a run's progress.
        run.progress = min(
            35, 5 + int(30 * counts.get("fetched", 0) / max(1, self.max_pages))
        )
        run.updated_at = now()

    def mark_complete(self) -> bool:
        with Session(self.engine) as session:
            run = _locked_run(session, self.run_id, self.token)
            if run is None:
                return False
            self.state["complete"] = True
            self._save_progress(session, run)
            session.commit()
        return True

    def mark_failed(self, issue) -> bool:
        """End this source with a whole-site failure; recovery will not retry it."""
        with Session(self.engine) as session:
            run = _locked_run(session, self.run_id, self.token)
            if run is None:
                return False
            self.state["complete"] = True
            self.state["failed"] = {"code": issue.code, "message": issue.message}
            self._save_progress(session, run)
            session.commit()
        return True


def outcomes_for(rows) -> list[tuple[PreviewOutcome, WebsiteCrawlFrontier]]:
    """Outcomes in discovery order, as the in-memory crawl reports them."""
    results = []
    for row in rows:
        location = row.final_url or row.canonical_url
        results.append(
            (
                PreviewOutcome(
                    external_id=location,
                    display_name=location,
                    canonical_location=location,
                    media_type=row.media_type,
                    status="included" if row.status == "fetched" else row.status,
                    reason=row.reason or "",
                    size_bytes=row.size_bytes,
                    depth=row.depth,
                    error_code=row.error_code,
                    attempts=row.attempts,
                ),
                row,
            )
        )
        if row.seen_again and row.canonical_url:
            results.append(
                (duplicate_outcome(row.canonical_url, row.duplicate_url), None)
            )
    return results


def page_artifact(row: WebsiteCrawlFrontier, prior_body=None) -> WebsiteArtifact:
    """The fetched page; an unchanged page's body comes from `prior_body(url)`."""
    if row.storage_name is None and row.validator_unchanged and prior_body:
        content = prior_body(row.canonical_url, row.final_url)
    else:
        content = artifact_storage.read(row)
    return WebsiteArtifact(
        canonical_location=row.final_url,
        content=content,
        media_type=row.media_type,
        etag=row.etag,
        last_modified=row.last_modified,
        validator_unchanged=row.validator_unchanged,
        depth=row.depth or 0,
    )


def clear_body(row: WebsiteCrawlFrontier) -> str | None:
    """Mark a stored page body for deletion; call `finish_release` after commit.

    The file name stays on the row until the file is gone, so a crash between
    the commit and the deletion leaves a row the dispatcher sweep still finds.
    """
    name = row.storage_name
    if name:
        row.artifact_state = "deleting"
        row.artifact_wrapped_key = None
        row.artifact_wrap_nonce = None
        row.artifact_content_nonce = None
    return name


def _forget(row: WebsiteCrawlFrontier) -> None:
    row.storage_name = None
    row.artifact_state = "deleted"
    row.artifact_wrapped_key = None
    row.artifact_wrap_nonce = None
    row.artifact_content_nonce = None


def delete_body(name: str | None) -> bool:
    if not name:
        return False
    try:
        (settings.storage_path / name).unlink(missing_ok=True)
        return True
    except OSError:
        logging.warning("A released crawl body could not be deleted.")
        return False


def finish_release(db_engine, row_id, name: str | None) -> None:
    """Delete a released body's file, then drop its name from the row."""
    if not delete_body(name):
        return
    with Session(_worker_engine(db_engine)) as session:
        session.execute(
            update(WebsiteCrawlFrontier)
            .where(
                WebsiteCrawlFrontier.id == row_id,
                WebsiteCrawlFrontier.storage_name == name,
            )
            .values(
                storage_name=None,
                artifact_state="deleted",
                artifact_wrapped_key=None,
                artifact_wrap_nonce=None,
                artifact_content_nonce=None,
            )
        )
        session.commit()


def release_terminal_bodies(db_engine, *, limit: int = 200) -> int:
    """Delete stored page bodies of runs that have ended; revisions keep their own.

    Files are deleted before the rows commit: nothing reads a finished run's
    crawl copies, and if the commit fails the next sweep deletes nothing new.
    """
    released = 0
    with Session(_worker_engine(db_engine)) as session:
        rows = session.scalars(
            select(WebsiteCrawlFrontier)
            .join(IngestionRun, IngestionRun.id == WebsiteCrawlFrontier.run_id)
            .where(
                WebsiteCrawlFrontier.storage_name.is_not(None),
                IngestionRun.status.in_(TERMINAL_RUN_STATUSES),
            )
            .limit(limit)
            .with_for_update(of=WebsiteCrawlFrontier, skip_locked=True)
        ).all()
        for row in rows:
            if delete_body(row.storage_name):
                _forget(row)
                released += 1
        session.commit()
    return released
