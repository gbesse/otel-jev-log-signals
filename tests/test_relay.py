import io
import json
import unittest
from unittest.mock import Mock

from relay import (DecisionError, InvalidPayload, TemplateCache, annotate,
                   make_app, validate_upstream)


def fixture():
    with open("examples/logs.json", encoding="utf-8") as source:
        return json.load(source)


class RelayTests(unittest.TestCase):
    def test_deduplicates_templates_and_preserves_logs(self):
        evaluate = Mock(return_value=("incident", 0.97))
        result = annotate(fixture(), TemplateCache(evaluate))
        records = result["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(records[0]["body"]["stringValue"], "payment call failed after 3 retries")
        self.assertEqual(records[1]["attributes"][-3]["value"]["stringValue"], "incident")
        self.assertEqual(records[0]["attributes"][-2]["value"]["doubleValue"], 0.97)

    def test_uncertain_goes_to_review_and_no_template_is_untouched(self):
        payload = fixture()
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        records.append({"body": {"stringValue": "plain log"}})
        result = annotate(payload, TemplateCache(lambda _: ("noise", 0.75)))
        output = result["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        self.assertEqual(output[0]["attributes"][-3]["value"]["stringValue"], "review")
        self.assertEqual(output[2], records[2])

    def test_conflict_rejected_before_jev_call(self):
        payload = fixture()
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        records[1]["attributes"].append({"key": "jev.log.outcome", "value": {"stringValue": "noise"}})
        evaluate = Mock(return_value=("incident", 0.97))
        with self.assertRaises(InvalidPayload):
            annotate(payload, TemplateCache(evaluate))
        evaluate.assert_not_called()

    def test_http_forwards_and_failure_is_retryable(self):
        payload = json.dumps(fixture()).encode()
        sent = Mock()
        app = make_app(TemplateCache(lambda _: ("incident", 0.95)),
                       "http://127.0.0.1:4318/v1/logs", send=sent)

        def call():
            status = []
            environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/v1/logs",
                       "CONTENT_LENGTH": str(len(payload)), "CONTENT_TYPE": "application/json",
                       "wsgi.input": io.BytesIO(payload)}
            body = b"".join(app(environ, lambda code, headers: status.append(code)))
            return status[0], body

        self.assertEqual(call()[0], "200 OK")
        self.assertEqual(sent.call_args.args[1]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]["attributes"][-3]["value"]["stringValue"], "incident")
        sent.side_effect = OSError("upstream unavailable")
        self.assertEqual(call()[0], "503 Service Unavailable")

    def test_jev_failure_is_retryable(self):
        payload = json.dumps(fixture()).encode()
        app = make_app(TemplateCache(lambda _: (_ for _ in ()).throw(DecisionError("failed"))),
                       "http://localhost:4318/v1/logs")
        status = []
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/v1/logs",
                   "CONTENT_LENGTH": str(len(payload)), "CONTENT_TYPE": "application/json",
                   "wsgi.input": io.BytesIO(payload)}
        b"".join(app(environ, lambda code, headers: status.append(code)))
        self.assertEqual(status[0], "503 Service Unavailable")

    def test_upstream_url_must_be_safe(self):
        self.assertEqual(validate_upstream("http://localhost:4318/v1/logs"),
                         "http://localhost:4318/v1/logs")
        for url in ("http://example.org/v1/logs", "https://user:pass@example.org/v1/logs",
                    "https://example.org/other", "file:///v1/logs"):
            with self.assertRaises(ValueError):
                validate_upstream(url)


if __name__ == "__main__":
    unittest.main()
