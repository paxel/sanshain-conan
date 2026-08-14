"""The 2.2 surface: streams, retire, harvested subscriptions, line endings."""

import unittest
from unittest import mock

from sanshainconan.client import (
    SanshainClient,
    SanshainError,
    normalize_line_endings,
    resolve_stream,
)


def make_response(status_code=200, json_data=None, text="", headers=None):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json body")
    return resp


PROVIDE_OK = {
    "version": "1.0.0",
    "stability": "snapshot",
    "content_hash": "sha256:abc",
    "changes": {"inserts": 0, "updates": 0, "deletes": 0},
}


class TestResolveStream(unittest.TestCase):
    def test_defaults_to_no_stream(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_stream(), (False, None))

    def test_reads_the_environment(self):
        with mock.patch.dict("os.environ", {"SANSHAIN_TRUNK": "true"}, clear=True):
            self.assertEqual(resolve_stream(), (True, None))
        with mock.patch.dict("os.environ", {"SANSHAIN_TAG": "R"}, clear=True):
            self.assertEqual(resolve_stream(), (False, "R"))

    def test_the_flag_beats_the_environment(self):
        with mock.patch.dict("os.environ", {"SANSHAIN_TAG": "from-env"}, clear=True):
            self.assertEqual(resolve_stream(tag="from-flag"), (False, "from-flag"))

    def test_trunk_and_tag_together_are_refused_locally(self):
        # The server answers 400 for both; naming the misconfiguration here
        # beats spending a round trip on it.
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SanshainError) as ctx:
                resolve_stream(trunk_flag=True, tag="R")
            self.assertIn("never both", str(ctx.exception))
            self.assertIn("R", str(ctx.exception))
        with mock.patch.dict("os.environ", {"SANSHAIN_TAG": "R"}, clear=True):
            with self.assertRaises(SanshainError):
                resolve_stream(trunk_flag=True)


class TestStreamsOnTheWire(unittest.TestCase):
    @mock.patch("requests.post")
    def test_provide_carries_the_declared_stream(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)
        client = SanshainClient("http://localhost:8080")

        client.provide("svc", "openapi: 3.0.0", "snapshot", trunk=True)
        self.assertEqual(mock_post.call_args[1]["json"].get("trunk"), True)

        client.provide("svc", "openapi: 3.0.0", "snapshot", tag="R")
        self.assertEqual(mock_post.call_args[1]["json"].get("tag"), "R")

        # Undeclared: both fields absent, not false/None.
        client.provide("svc", "openapi: 3.0.0", "snapshot")
        payload = mock_post.call_args[1]["json"]
        self.assertNotIn("trunk", payload)
        self.assertNotIn("tag", payload)

    @mock.patch("requests.get")
    def test_single_require_carries_the_stream_in_the_query(self, mock_get):
        mock_get.return_value = make_response(200, text="paths: {}")
        client = SanshainClient("http://localhost:8080")

        client.require("c", "p", "1.0.0", "/x", "GET", trunk=True)
        self.assertEqual(mock_get.call_args[1]["params"].get("trunk"), True)

        client.require("c", "p", "1.0.0", "/x", "GET", tag="R")
        self.assertEqual(mock_get.call_args[1]["params"].get("tag"), "R")

    @mock.patch("requests.post")
    def test_bundle_carries_the_stream_in_the_body(self, mock_post):
        # The bundle endpoint reads the stream from the body — its handler has
        # no query extractor, so query parameters would be silently dropped and
        # a trunk build would record no trunk pins.
        mock_post.return_value = make_response(200, text="paths: {}")
        client = SanshainClient("http://localhost:8080")
        endpoints = [{"path": "/x", "method": "GET"}, {"path": "/y", "method": "GET"}]

        client.require_bundle("c", "p", "1.0.0", endpoints, trunk=True)
        self.assertEqual(mock_post.call_args[1]["json"].get("trunk"), True)

        client.require_bundle("c", "p", "1.0.0", endpoints, tag="R")
        self.assertEqual(mock_post.call_args[1]["json"].get("tag"), "R")

        client.require_bundle("c", "p", "1.0.0", endpoints)
        payload = mock_post.call_args[1]["json"]
        self.assertNotIn("trunk", payload)
        self.assertNotIn("tag", payload)


class TestRetire(unittest.TestCase):
    @mock.patch("requests.post")
    def test_retire_sends_retired_with_no_document(self, mock_post):
        mock_post.return_value = make_response(
            202, {"tag_cleared": "messaging", "trunk_pins_closed": 2, "contracts_released": 1}
        )
        client = SanshainClient("http://localhost:8080")

        shed = client.retire("notifier", "asyncapi")

        args, kwargs = mock_post.call_args
        self.assertTrue(args[0].endswith("/provide/asyncapi"))
        self.assertEqual(kwargs["json"], {"producername": "notifier", "retired": True})
        self.assertEqual(shed["tag_cleared"], "messaging")

    @mock.patch("requests.post")
    def test_retire_dry_run_is_sent_as_such(self, mock_post):
        mock_post.return_value = make_response(202, {"trunk_pins_closed": 0, "contracts_released": 0})
        client = SanshainClient("http://localhost:8080")

        client.retire("svc", dry_run=True)

        self.assertEqual(
            mock_post.call_args[1]["json"],
            {"producername": "svc", "retired": True, "dry_run": True},
        )

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_forbidden_names_the_role_and_the_maintainer_grant(self, mock_post, mock_get):
        # The lazy wrong-server check answers 2.x, keeping the original error.
        mock_get.return_value = make_response(200, {"version": "2.2.0"})
        mock_post.return_value = make_response(
            403, {"error": "requires the 'releaser' role"}, text='{"error":"requires the releaser role"}'
        )
        client = SanshainClient("http://localhost:8080")

        with self.assertRaises(SanshainError) as ctx:
            client.retire("svc")
        message = str(ctx.exception)
        self.assertIn("releaser", message)
        self.assertIn("maintainer", message)
        self.assertIn("snapshot", message)


class TestLineEndings(unittest.TestCase):
    def test_crlf_is_normalized_before_upload(self):
        # Byte-for-byte comparison server-side: a CRLF checkout must hash the
        # same as an LF one, or the same commit conflicts with itself
        # depending on which runner published it.
        self.assertEqual(normalize_line_endings("a\r\nb\rc\n"), "a\nb\nc\n")
        lf = "a\nb\n"
        self.assertIs(normalize_line_endings(lf), lf)

    @mock.patch("requests.post")
    def test_provide_uploads_lf_content(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)
        client = SanshainClient("http://localhost:8080")

        client.provide("svc", "openapi: 3.0.3\r\ninfo:\r\n  title: T\r", "snapshot")

        sent = mock_post.call_args[1]["json"]["openapi_yaml"]
        self.assertEqual(sent, "openapi: 3.0.3\ninfo:\n  title: T\n")


class TestHarvestedSubscriptions(unittest.TestCase):
    @mock.patch("requests.post")
    def test_the_response_carries_the_harvest_through(self, mock_post):
        mock_post.return_value = make_response(
            202,
            dict(
                PROVIDE_OK,
                harvested_subscriptions=[
                    {"channel": "user/signup", "message_name": "UserSignedUp", "owner": "accounts"},
                    {"channel": "order/placed", "message_name": "OrderPlaced", "drift": "expects 'total'"},
                ],
            ),
        )
        client = SanshainClient("http://localhost:8080")

        res = client.provide_asyncapi("svc", "asyncapi: 2.6.0", "snapshot")

        subs = res["harvested_subscriptions"]
        self.assertEqual(len(subs), 2)
        self.assertEqual(subs[0]["owner"], "accounts")
        self.assertEqual(subs[1]["drift"], "expects 'total'")


if __name__ == "__main__":
    unittest.main()
