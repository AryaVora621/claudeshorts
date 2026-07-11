from __future__ import annotations

import json
import logging

import pytest

from claudeshorts import logging_setup


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset logger state between tests."""
    yield
    logger = logging.getLogger("claudeshorts")
    logger.handlers.clear()
    logger._claudeshorts_configured = False


def test_bind_sets_and_restores_contextvars():
    with logging_setup.bind(job_id=1, worker_id="w1"):
        record = logging.LogRecord("x", logging.INFO, "", 0, "msg", None, None)
        logging_setup._ContextFilter().filter(record)
        assert record.job_id == 1
        assert record.worker_id == "w1"
        assert record.platform is None
    record2 = logging.LogRecord("x", logging.INFO, "", 0, "msg", None, None)
    logging_setup._ContextFilter().filter(record2)
    assert record2.job_id is None


def test_bind_nests_and_restores_outer_value():
    with logging_setup.bind(job_id=1):
        with logging_setup.bind(job_id=2):
            record = logging.LogRecord("x", logging.INFO, "", 0, "m", None, None)
            logging_setup._ContextFilter().filter(record)
            assert record.job_id == 2
        record = logging.LogRecord("x", logging.INFO, "", 0, "m", None, None)
        logging_setup._ContextFilter().filter(record)
        assert record.job_id == 1


def test_configure_logging_is_idempotent():
    logging_setup.configure_logging()
    handlers_after_first = list(logging.getLogger("claudeshorts").handlers)
    logging_setup.configure_logging()
    assert logging.getLogger("claudeshorts").handlers == handlers_after_first


def test_json_formatter_produces_parseable_output(capsys):
    logging_setup.configure_logging(fmt="json")
    log = logging.getLogger("claudeshorts.test")
    with logging_setup.bind(job_id=5, platform="youtube"):
        log.info("hello")
    captured = capsys.readouterr()
    line = [l for l in captured.err.splitlines() if l.strip()][-1]
    parsed = json.loads(line)
    assert parsed["message"] == "hello"
    assert parsed["job_id"] == 5
    assert parsed["platform"] == "youtube"


def test_json_formatter_includes_traceback(capsys):
    logging_setup.configure_logging(fmt="json")
    log = logging.getLogger("claudeshorts.test")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("failed")
    line = [l for l in capsys.readouterr().err.splitlines() if l.strip()][-1]
    parsed = json.loads(line)
    assert parsed["message"] == "failed"
    assert "RuntimeError: boom" in parsed["exc_info"]
