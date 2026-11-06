"""Queue persistence, recovery, privacy and exclusive consumption."""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import background_jobs as jobs


@pytest.fixture
def store(tmp_path):
    return jobs.JobStore(tmp_path / "jobs.sqlite3")


def test_pending_work_survives_restart_and_terminal_record_discards_payload(
    store,
):
    job = store.enqueue(
        "mail", {"to": "private@example.invalid", "body": "secret"}
    )
    restarted = jobs.JobStore(store.path)
    calls = []
    assert restarted.run_once(
        {"mail": lambda task: calls.append(task["payload"])}
    )
    assert calls == [{"to": "private@example.invalid", "body": "secret"}]
    result = restarted.get(job["id"])
    assert result["state"] == "done"
    assert result["payload"] == {}
    assert not restarted.run_once(
        {"mail": lambda task: pytest.fail("duplicate delivery")}
    )


@pytest.mark.parametrize("kind", ["mail", "blog_mail"])
def test_interrupted_mail_is_uncertain_and_not_replayed(store, kind):
    job = store.enqueue(kind, {"secret": "private"}, dedupe_key="mail-one")
    store.claim()
    restarted = jobs.JobStore(store.path)
    assert not restarted.run_once(
        {kind: lambda task: pytest.fail("uncertain mail replayed")}
    )
    record = restarted.get(job["id"])
    assert record["state"] == "uncertain"
    assert record["payload"] == {}
    assert record["error_code"] == "interrupted"
    duplicate = restarted.enqueue(
        kind, {"secret": "private"}, dedupe_key="mail-one"
    )
    assert duplicate["id"] == job["id"]


def test_interrupted_archive_is_rebuilt_and_result_is_available(store):
    job = store.enqueue("archive", {"movie": "example"}, owner="member")
    store.claim()
    restarted = jobs.JobStore(store.path)
    assert restarted.run_once(
        {"archive": lambda task: {"filename": "ready.zip"}}
    )
    record = restarted.get(job["id"])
    assert record["state"] == "done"
    assert record["owner"] == "member"
    assert record["result"] == {"filename": "ready.zip"}


def test_queue_bound_and_active_or_completed_deduplication(store, monkeypatch):
    monkeypatch.setattr(jobs, "MAX_QUEUED_JOBS", 2)
    first = store.enqueue("mail", {}, dedupe_key="first")
    store.enqueue("mail", {})
    assert store.enqueue("mail", {}, dedupe_key="first")["id"] == first["id"]
    with pytest.raises(jobs.QueueFull):
        store.enqueue("mail", {})
    assert store.run_once({"mail": lambda task: None})
    assert store.enqueue("mail", {}, dedupe_key="first")["id"] == first["id"]
    assert store.enqueue("mail", {})["state"] == "pending"


def test_failed_job_can_be_explicitly_requeued_without_leaking_exception(
    store,
):
    job = store.enqueue(
        "mail", {"to": "private@example.invalid"}, dedupe_key="retry"
    )

    def fail(task):
        raise RuntimeError("private@example.invalid token=secret")

    store.run_once({"mail": fail})
    record = store.get(job["id"])
    assert record["state"] == "failed"
    assert record["payload"] == {}
    assert record["error_code"] == "handler_failed"
    retry = store.enqueue("mail", {}, dedupe_key="retry")
    assert retry["id"] != job["id"]


def test_terminal_records_expire_but_pending_work_does_not(store, monkeypatch):
    monkeypatch.setattr(jobs.time, "time", lambda: 100)
    done = store.enqueue("archive", {})
    store.run_once({"archive": lambda task: None})
    pending = store.enqueue("archive", {})
    monkeypatch.setattr(jobs.time, "time", lambda: 100 + jobs.TERMINAL_TTL + 1)
    store.enqueue("mail", {})
    assert store.get(done["id"]) is None
    assert store.get(pending["id"])["state"] == "pending"


def test_payload_limit_measures_utf8_bytes(store, monkeypatch):
    monkeypatch.setattr(jobs, "MAX_PAYLOAD_BYTES", 20)
    with pytest.raises(jobs.JobTooLarge):
        store.enqueue("mail", {"body": "č" * 10})
    assert store.claim() is None


def test_concurrent_claims_never_return_same_job(store):
    expected = {
        store.enqueue("archive", {"index": index})["id"] for index in range(8)
    }
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = list(pool.map(lambda _: store.claim()["id"], range(8)))
    assert set(claimed) == expected
    assert len(claimed) == len(set(claimed))


def test_two_consumers_never_overlap_and_waiting_worker_takes_over(store):
    second_store = jobs.JobStore(store.path)
    entered = threading.Event()
    release = threading.Event()
    delivered = threading.Event()
    job = store.enqueue("mail", {})

    def blocked(task):
        entered.set()
        assert release.wait(5)

    first_stop = store.start_worker({"mail": blocked})
    second_stop = None
    try:
        assert entered.wait(5)
        assert not second_store.run_once(
            {"mail": lambda task: pytest.fail("overlap")}
        )
        second_stop = second_store.start_worker(
            {"mail": lambda task: delivered.set()}
        )
        first_stop.set()
        release.set()
        for worker in store._workers:
            worker.join(5)
        assert store.get(job["id"])["state"] == "done"
        store.enqueue("mail", {})
        assert delivered.wait(5)
    finally:
        first_stop.set()
        release.set()
        if second_stop is not None:
            second_stop.set()
        for worker in store._workers + second_store._workers:
            worker.join(5)


def test_worker_continues_after_handler_failure(store):
    failed = store.enqueue("mail", {"fail": True})
    ready = threading.Event()
    following = store.enqueue("mail", {"fail": False})

    def deliver(job):
        if job["payload"]["fail"]:
            raise RuntimeError("delivery failed")
        ready.set()

    stop = store.start_worker({"mail": deliver})
    try:
        assert ready.wait(5)
    finally:
        stop.set()
        for worker in store._workers:
            worker.join(5)
    assert store.get(failed["id"])["state"] == "failed"
    assert store.get(following["id"])["state"] == "done"


def test_invalid_handler_result_finishes_record_and_queue_continues(store):
    job = store.enqueue("archive", {})
    assert store.run_once({"archive": lambda task: object()})
    assert store.get(job["id"])["error_code"] == "invalid_result"


def test_initialization_does_not_reset_another_workers_running_job(store):
    job = store.enqueue("archive", {})
    store.claim()
    jobs.JobStore(store.path)
    assert store.get(job["id"])["state"] == "running"


def test_running_archive_does_not_delay_password_reset_mail(store):
    archive_started = threading.Event()
    finish_archive = threading.Event()
    mail_sent = threading.Event()
    store.enqueue("archive", {})

    def archive(job):
        archive_started.set()
        assert finish_archive.wait(5)

    stop = store.start_worker(
        {
            "archive": archive,
            "mail": lambda job: mail_sent.set(),
        }
    )
    try:
        assert archive_started.wait(5)
        store.enqueue("mail", {"purpose": "password_reset"})
        assert mail_sent.wait(3)
        assert not finish_archive.is_set()
    finally:
        stop.set()
        finish_archive.set()
        for worker in store._workers:
            worker.join(5)


def test_mail_lane_recovery_does_not_reset_running_archive(store):
    archive = store.enqueue("archive", {})
    mail = store.enqueue("mail", {})
    store.claim("archive")
    store.claim("mail")
    restarted = jobs.JobStore(store.path)
    assert not restarted.run_once({"mail": lambda job: None})
    assert restarted.get(mail["id"])["state"] == "uncertain"
    assert restarted.get(archive["id"])["state"] == "running"


def test_partial_delivery_is_uncertain_and_blocks_ordinary_retry(store):
    job = store.enqueue(
        "blog_mail", {"email": "private@example.invalid"}, dedupe_key="partial"
    )

    def partial_delivery(job):
        raise jobs.DeliveryUncertain(
            "private@example.invalid might have received mail"
        )

    assert store.run_once({"blog_mail": partial_delivery})
    record = store.get(job["id"])
    assert record["state"] == "uncertain"
    assert record["payload"] == {}
    assert record["error_code"] == "delivery_uncertain"
    retry = store.enqueue("blog_mail", {}, dedupe_key="partial")
    assert retry["id"] == job["id"]
    assert not store.run_once({"blog_mail": partial_delivery})


def test_account_mail_is_claimed_before_older_blog_campaign(store):
    campaign = store.enqueue("blog_mail", {})
    reset = store.enqueue("mail", {"purpose": "password_reset"})
    calls = []
    handlers = {
        "mail": lambda job: calls.append(job["id"]),
        "blog_mail": lambda job: calls.append(job["id"]),
    }
    assert store.run_once(handlers)
    assert calls == [reset["id"]]
    assert store.get(campaign["id"])["state"] == "pending"


def test_worker_retries_terminal_write_without_repeating_delivery(
    store, monkeypatch
):
    job = store.enqueue("mail", {})
    attempts = []
    deliveries = []
    completed = threading.Event()
    finish = store.finish

    def interrupted_finish(job_id, result=None):
        attempts.append(job_id)
        if len(attempts) == 1:
            raise sqlite3.OperationalError("database is locked")
        finish(job_id, result)
        completed.set()

    monkeypatch.setattr(store, "finish", interrupted_finish)
    stop = store.start_worker(
        {"mail": lambda task: deliveries.append(task["id"])}
    )
    try:
        assert completed.wait(4)
    finally:
        stop.set()
        for worker in store._workers:
            worker.join(5)
    assert attempts == [job["id"], job["id"]]
    assert deliveries == [job["id"]]
    assert store.get(job["id"])["state"] == "done"


def test_manual_run_propagates_terminal_storage_failure(store, monkeypatch):
    job = store.enqueue("mail", {})

    def busy(job_id, result=None):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "finish", busy)
    with pytest.raises(sqlite3.OperationalError):
        store.run_once({"mail": lambda task: None})
    assert store.get(job["id"])["state"] == "running"


def test_archive_can_be_requeued_after_finished_artifact_is_evicted(
    store, tmp_path
):
    artifact = tmp_path / "movie.zip"
    artifact.write_bytes(b"prepared archive")
    first = store.enqueue("archive", {}, dedupe_key="movie")
    assert (
        store.enqueue("archive", {}, dedupe_key="movie")["id"] == first["id"]
    )
    store.run_once({"archive": lambda job: {"path": str(artifact)}})
    artifact.unlink()
    replacement = store.enqueue("archive", {}, dedupe_key="movie")
    assert replacement["id"] != first["id"]
    assert replacement["state"] == "pending"
    assert store.get(first["id"])["state"] == "done"
