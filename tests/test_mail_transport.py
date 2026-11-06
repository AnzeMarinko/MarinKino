"""Optional Redis telemetry cannot overwrite the SMTP delivery outcome."""

import importlib.util
import smtplib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from background_jobs import DeliveryUncertain
from mail_jobs import _deliver

SOURCE = Path(__file__).resolve().parents[1] / "src/utils.py"


@pytest.fixture
def mailer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("MAIL_SENDER", "admin@example.invalid")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/test_users.json").write_text("{}")
    spec = importlib.util.spec_from_file_location(
        "mail_transport_test", SOURCE
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.redis_client = Mock()
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = False
    smtp.send_message.return_value = {}
    monkeypatch.setattr(module.smtplib, "SMTP", Mock(return_value=smtp))
    return SimpleNamespace(module=module, smtp=smtp)


def test_recipient_counter_outage_does_not_block_delivery(mailer):
    mailer.module.redis_client.sadd.side_effect = RedisConnectionError()
    assert mailer.module.send_mail(to="reader@example.invalid") == {}
    mailer.smtp.send_message.assert_called_once()


def test_rejection_counter_outage_preserves_partial_delivery(mailer):
    rejected = {"bad@example.invalid": (550, b"recipient rejected")}
    mailer.smtp.send_message.return_value = rejected
    mailer.module.redis_client.hset.side_effect = RedisConnectionError()
    assert (
        mailer.module.send_mail(
            to=["good@example.invalid", "bad@example.invalid"]
        )
        == rejected
    )
    with patch.dict(sys.modules, {"utils": mailer.module}):
        with pytest.raises(DeliveryUncertain):
            _deliver({"to": ["good@example.invalid", "bad@example.invalid"]})


def test_error_counter_outage_does_not_mask_smtp_disconnect(mailer):
    disconnected = smtplib.SMTPServerDisconnected("connection lost")
    mailer.smtp.send_message.side_effect = disconnected
    mailer.module.redis_client.hset.side_effect = RedisConnectionError()
    with pytest.raises(smtplib.SMTPServerDisconnected) as error:
        mailer.module.send_mail(to="reader@example.invalid")
    assert error.value is disconnected
    with patch.dict(sys.modules, {"utils": mailer.module}):
        with pytest.raises(DeliveryUncertain):
            _deliver({"to": "reader@example.invalid"})


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPRecipientsRefused(
            {"reader@example.invalid": (550, b"rejected")}
        ),
        smtplib.SMTPAuthenticationError(535, b"authentication failed"),
    ],
)
def test_explicit_smtp_rejection_stays_retryable_despite_telemetry_outage(
    mailer, failure
):
    mailer.smtp.send_message.side_effect = failure
    mailer.module.redis_client.hset.side_effect = RedisConnectionError()
    with patch.dict(sys.modules, {"utils": mailer.module}):
        with pytest.raises(type(failure)) as error:
            _deliver({"to": "reader@example.invalid"})
    assert error.value is failure
