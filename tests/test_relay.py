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
        sent = Mock(return_value=b"{}")
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


class AcknowledgementTests(unittest.TestCase):
    def test_partial_and_warning_remain_visible_in_all_languages(self):
        from relay import acknowledgement, TEXT
        for lang in TEXT:
            result = json.loads(acknowledgement(b'{"partialSuccess":{"rejectedLogRecords":"1","errorMessage":"private upstream log"}}', 2, lang))
            self.assertEqual(result['partialSuccess']['rejectedLogRecords'], '1')
            self.assertEqual(result['partialSuccess']['errorMessage'], TEXT[lang])
            self.assertNotIn('private upstream log', json.dumps(result))
            warning = json.loads(acknowledgement(b'{"partialSuccess":{"errorMessage":"warning"}}', 2, lang))
            self.assertEqual(warning['partialSuccess']['rejectedLogRecords'], '0')

    def test_invalid_partial_is_not_acknowledged_as_full_success(self):
        from relay import acknowledgement
        for value in ({'partialSuccess': []}, {'partialSuccess': {'rejectedLogRecords': True}},
                      {'partialSuccess': {'rejectedLogRecords': '-1'}}, {'partialSuccess': {'rejectedLogRecords': '3'}},
                      {'partialSuccess': {'rejectedLogRecords': 0.5}}, {'partialSuccess': {'errorMessage': []}}, []):
            with self.subTest(value=value), self.assertRaises((DecisionError, ValueError)):
                acknowledgement(json.dumps(value), 2)

    def test_wsgi_returns_partial_success_without_retry_status(self):
        payload = json.dumps(fixture()).encode(); status = []
        app = make_app(TemplateCache(lambda _: ('incident', .95)), 'http://localhost:4318/v1/logs',
                       send=lambda *args: b'{"partialSuccess":{"rejectedLogRecords":"1"}}', lang='fr')
        body = b''.join(app({'REQUEST_METHOD':'POST', 'PATH_INFO':'/v1/logs', 'CONTENT_LENGTH':str(len(payload)),
                            'CONTENT_TYPE':'application/json', 'wsgi.input':io.BytesIO(payload)},
                           lambda code, headers: status.append(code)))
        self.assertEqual(status, ['200 OK'])
        self.assertEqual(json.loads(body)['partialSuccess']['rejectedLogRecords'], '1')

    def test_bounded_upstream_read(self):
        from relay import forward, MAX_RESPONSE
        response = Mock();response.__enter__ = Mock(return_value=response);response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'x' * (MAX_RESPONSE + 1)
        with self.assertRaises(DecisionError):forward('http://localhost:4318/v1/logs', {}, opener=lambda *a, **k:response)
        response.read.assert_called_once_with(MAX_RESPONSE + 1)

    def test_redirect_is_refused_instead_of_reposting(self):
        from relay import NoRedirect
        from urllib.request import Request
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError):
            NoRedirect().redirect_request(Request('https://example.test/v1/logs'), None, 307, 'redirect', {}, 'http://other.test/v1/logs')

    def test_invalid_acknowledgement_is_non_retryable(self):
        payload=json.dumps(fixture()).encode();status=[]
        app=make_app(TemplateCache(lambda _: ('incident', .95)), 'http://localhost:4318/v1/logs', send=lambda *args:b'not JSON')
        b''.join(app({'REQUEST_METHOD':'POST','PATH_INFO':'/v1/logs','CONTENT_LENGTH':str(len(payload)),
                     'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(payload)},lambda code,headers:status.append(code)))
        self.assertEqual(status,['500 Internal Server Error'])
