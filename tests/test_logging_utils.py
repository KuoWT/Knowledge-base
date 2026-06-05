import json
import logging
import unittest

from knowledge_base_api.logging_utils import JsonFormatter


class LoggingUtilsTests(unittest.TestCase):
    def test_json_formatter_includes_structured_fields(self):
        record = logging.LogRecord(
            name="kb_api.server",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="request completed",
            args=(),
            exc_info=None,
        )
        record.remote = "127.0.0.1"
        record.method = "GET"
        record.path = "/health"
        record.status = 200
        record.duration_ms = 3.14

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["logger"], "kb_api.server")
        self.assertEqual(payload["message"], "request completed")
        self.assertEqual(payload["remote"], "127.0.0.1")
        self.assertEqual(payload["method"], "GET")
        self.assertEqual(payload["path"], "/health")
        self.assertEqual(payload["status"], 200)
        self.assertEqual(payload["duration_ms"], 3.14)
