"""A bounded durable queue with separate mail and archive consumers.

Pending work survives process restarts. Interrupted archives may be rebuilt;
interrupted mail is uncertain and is never automatically sent a second time.
"""

import fcntl
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from uuid import uuid4

log = logging.getLogger(__name__)
MAX_QUEUED_JOBS = 128
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 64 * 1024
TERMINAL_TTL = 7 * 86400


class QueueFull(Exception):  # noqa: N818 - established queue outcome API
    """The bounded queue cannot accept another job yet."""


class JobTooLarge(ValueError):  # noqa: N818 - established queue outcome API
    """The job exceeds the queue's per-record storage limit."""


class DeliveryUncertain(Exception):  # noqa: N818 - delivery outcome API
    """Some recipients may have received mail; ordinary retry is unsafe."""


def _encode(value, maximum):
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > maximum:
        raise JobTooLarge("Job data exceeds the storage limit")
    return encoded


class JobStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        self.path.chmod(0o600)
        self._worker_guard = threading.Lock()
        self._workers = []
        self._stop = None
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    dedupe_key TEXT,
                    state TEXT NOT NULL CHECK (state IN (
                        'pending', 'running', 'done', 'failed', 'uncertain'
                    )),
                    result TEXT,
                    error_code TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_pending
                    ON jobs(state, created_at);
                CREATE INDEX IF NOT EXISTS jobs_dedupe
                    ON jobs(dedupe_key, state);
            """
            )

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _job(row):
        if row is None:
            return None
        job = dict(row)
        job["payload"] = json.loads(job["payload"])
        job["result"] = json.loads(job["result"]) if job["result"] else None
        return job

    @staticmethod
    def _purge(connection, now):
        connection.execute(
            "DELETE FROM jobs WHERE state IN ('done', 'failed', 'uncertain') "
            "AND updated_at < ?",
            (now - TERMINAL_TTL,),
        )

    def enqueue(self, kind, payload, owner="", dedupe_key=None):
        encoded = _encode(payload, MAX_PAYLOAD_BYTES)
        now = time.time()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._purge(connection, now)
            if dedupe_key is not None:
                states = (
                    "state IN ('pending', 'running') "
                    if kind == "archive"
                    else (
                        "state IN ('pending', 'running', 'done', 'uncertain') "
                    )
                )
                row = connection.execute(
                    "SELECT * FROM jobs WHERE dedupe_key = ? AND kind = ? AND "
                    + states
                    + "ORDER BY created_at DESC LIMIT 1",
                    (dedupe_key, kind),
                ).fetchone()
                if row is not None:
                    return self._job(row)
            count = connection.execute(
                "SELECT COUNT(*) FROM jobs "
                "WHERE state IN ('pending', 'running')"
            ).fetchone()[0]
            if count >= MAX_QUEUED_JOBS:
                raise QueueFull("Background queue is full")
            job_id = uuid4().hex
            connection.execute(
                "INSERT INTO jobs "
                "(id, kind, owner, payload, dedupe_key, state, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (job_id, kind, owner, encoded, dedupe_key, now, now),
            )
            return self._job(
                connection.execute(
                    "SELECT * FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
            )

    def get(self, job_id):
        with self._connection() as connection:
            return self._job(
                connection.execute(
                    "SELECT * FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
            )

    def claim(self, lane=None):
        now = time.time()
        predicate = self._lane_predicate(lane)
        priority = (
            "CASE kind WHEN 'mail' THEN 0 ELSE 1 END, "
            if lane == "mail"
            else ""
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._purge(connection, now)
            row = connection.execute(
                "SELECT * FROM jobs WHERE state = 'pending' "
                + predicate
                + "ORDER BY "
                + priority
                + "created_at, id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE jobs SET state = 'running', updated_at = ? "
                "WHERE id = ?",
                (now, row["id"]),
            )
            job = self._job(row)
            job.update(state="running", updated_at=now)
            return job

    def finish(self, job_id, result=None):
        encoded = (
            _encode(result, MAX_RESULT_BYTES) if result is not None else None
        )
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET state = 'done', payload = '{}', result = ?, "
                "error_code = NULL, updated_at = ? "
                "WHERE id = ? AND state = 'running'",
                (encoded, time.time(), job_id),
            )

    def fail(self, job_id, error_code):
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET state = 'failed', payload = '{}', "
                "result = NULL, error_code = ?, updated_at = ? "
                "WHERE id = ? AND state = 'running'",
                (error_code, time.time(), job_id),
            )

    def _uncertain(self, job_id):
        with self._connection() as connection:
            connection.execute(
                "UPDATE jobs SET state = 'uncertain', "
                "payload = '{}', result = NULL, "
                "error_code = 'delivery_uncertain', updated_at = ? "
                "WHERE id = ? AND state = 'running'",
                (time.time(), job_id),
            )

    @contextmanager
    def _consumer_lock(self, lane):
        descriptor = os.open(
            f"{self.path}.worker-{lane}.lock", os.O_CREAT | os.O_RDWR, 0o600
        )
        acquired = False
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                pass
            yield acquired
        finally:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _lane_predicate(lane):
        if lane == "archive":
            return "AND kind = 'archive' "
        if lane == "mail":
            return "AND kind <> 'archive' "
        return ""

    @staticmethod
    def _lanes(handlers):
        lanes = []
        if any(kind != "archive" for kind in handlers):
            lanes.append("mail")
        if "archive" in handlers:
            lanes.append("archive")
        return lanes

    def _recover_running(self, lane):
        with self._connection() as connection:
            now = time.time()
            if lane == "archive":
                connection.execute(
                    "UPDATE jobs SET state = 'pending', updated_at = ? "
                    "WHERE state = 'running' AND kind = 'archive'",
                    (now,),
                )
            else:
                connection.execute(
                    "UPDATE jobs SET state = 'uncertain', payload = '{}', "
                    "error_code = 'interrupted', updated_at = ? "
                    "WHERE state = 'running' AND kind <> 'archive'",
                    (now,),
                )

    @staticmethod
    def _persist_terminal(write, stop):
        warned = False
        while True:
            try:
                write()
                return
            except sqlite3.Error:
                if stop is None:
                    raise
                if not warned:
                    log.warning("Waiting to persist background job outcome")
                    warned = True
                if stop.wait(1):
                    return

    def _finish_result(self, job_id, result):
        try:
            self.finish(job_id, result)
        except (TypeError, ValueError):
            self.fail(job_id, "invalid_result")

    def _run_claimed(self, handlers, lane, stop=None):
        job = self.claim(lane)
        if job is None:
            return False
        handler = handlers.get(job["kind"])
        if handler is None:
            self._persist_terminal(
                partial(self.fail, job["id"], "unsupported_job"), stop
            )
            return True
        try:
            result = handler(job)
        except DeliveryUncertain:
            write = partial(self._uncertain, job["id"])
        except Exception:
            # A worker boundary must finish this record and continue the queue.
            # Exceptions can contain private data: never persist their text.
            log.warning("Background job failed: %s", job["id"])
            write = partial(self.fail, job["id"], "handler_failed")
        else:
            write = partial(self._finish_result, job["id"], result)
        self._persist_terminal(write, stop)
        return True

    def run_once(self, handlers):
        for lane in self._lanes(handlers):
            with self._consumer_lock(lane) as acquired:
                if acquired:
                    self._recover_running(lane)
                    if self._run_claimed(handlers, lane):
                        return True
        return False

    def start_worker(self, handlers):
        with self._worker_guard:
            if any(worker.is_alive() for worker in self._workers):
                return self._stop
            stop = threading.Event()

            def consume(lane):
                while not stop.is_set():
                    with self._consumer_lock(lane) as acquired:
                        if not acquired:
                            stop.wait(1)
                            continue
                        recovered = False
                        while not stop.is_set():
                            try:
                                if not recovered:
                                    self._recover_running(lane)
                                    recovered = True
                                worked = self._run_claimed(
                                    handlers, lane, stop
                                )
                            except sqlite3.Error:
                                log.warning(
                                    "Background job storage unavailable"
                                )
                                worked = False
                            if not worked:
                                stop.wait(1)

            self._stop = stop
            self._workers = [
                threading.Thread(
                    target=consume,
                    args=(lane,),
                    name=f"background-{lane}",
                    daemon=True,
                )
                for lane in self._lanes(handlers)
            ]
            for worker in self._workers:
                worker.start()
            return stop
