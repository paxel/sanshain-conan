import unittest
from unittest import mock

from sanshainconan.client import SanshainClient, SanshainError, VersionConflictError


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
    "version": "1.2.0",
    "stability": "snapshot",
    "content_hash": "sha256:abc",
    "changes": {"inserts": 2, "updates": 1, "deletes": 0},
}


class TestProvide(unittest.TestCase):
    @mock.patch("requests.post")
    def test_provide_payload_carries_stability_and_no_branch_era_fields(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)

        client = SanshainClient("http://localhost:8080", token="test-token")  # nosec B106
        res = client.provide("my-service", "openapi: 3.0.0", "snapshot")

        self.assertEqual(res["version"], "1.2.0")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(
            kwargs["json"],
            {"producername": "my-service", "openapi_yaml": "openapi: 3.0.0", "stability": "snapshot"},
        )
        self.assertNotIn("branch", kwargs["json"])
        self.assertNotIn("base_version", kwargs["json"])
        self.assertNotIn("force", kwargs["json"])
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")

    @mock.patch("requests.post")
    def test_provide_ga_stability(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)

        client = SanshainClient("http://localhost:8080")
        client.provide("my-service", "openapi: 3.0.0", "ga")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["stability"], "ga")

    @mock.patch("requests.post")
    def test_provide_asyncapi_payload(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)

        client = SanshainClient("http://localhost:8080")
        client.provide_asyncapi("my-service", "asyncapi: 2.6.0", "snapshot")

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://localhost:8080/provide/asyncapi")
        self.assertEqual(
            kwargs["json"],
            {"producername": "my-service", "asyncapi_yaml": "asyncapi: 2.6.0", "stability": "snapshot"},
        )

    @mock.patch("requests.post")
    def test_provide_proto_payload(self, mock_post):
        mock_post.return_value = make_response(202, PROVIDE_OK)

        client = SanshainClient("http://localhost:8080")
        client.provide_proto("my-service", 'syntax = "proto3";', "snapshot")

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "http://localhost:8080/provide/grpc")
        self.assertEqual(
            kwargs["json"],
            {"producername": "my-service", "proto_content": 'syntax = "proto3";', "stability": "snapshot"},
        )

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_provide_409_surfaces_proposed_version(self, mock_post, mock_get):
        mock_post.return_value = make_response(409, {"error": "GA 1.2.0 is immutable", "proposed_version": "1.3.0"})

        client = SanshainClient("http://localhost:8080")
        with self.assertRaises(VersionConflictError) as ctx:
            client.provide("my-service", "openapi: 3.0.0", "ga")

        self.assertEqual(ctx.exception.proposed_version, "1.3.0")
        self.assertEqual(ctx.exception.server_message, "GA 1.2.0 is immutable")
        self.assertIn("1.3.0", str(ctx.exception))
        # A 409 with proposed_version is definitionally a 2.x answer — no /version probe.
        mock_get.assert_not_called()


class TestRequire(unittest.TestCase):
    @mock.patch("requests.get")
    def test_require_sends_version_and_no_branch_era_params(self, mock_get):
        mock_get.return_value = make_response(200, text="openapi: 3.0.0", headers={"ETag": '"e1"'})

        client = SanshainClient("http://localhost:8080")
        res = client.require("consumer", "producer", "1.2.3", "/bar", "GET")

        self.assertEqual(res["content"], "openapi: 3.0.0")
        self.assertEqual(res["etag"], '"e1"')
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(
            kwargs["params"],
            {
                "consumername": "consumer",
                "producername": "producer",
                "version": "1.2.3",
                "path": "/bar",
                "method": "GET",
            },
        )

    @mock.patch("requests.post")
    def test_require_bundle_sends_version(self, mock_post):
        mock_post.return_value = make_response(200, text="openapi: 3.0.0", headers={"ETag": '"e2"'})

        client = SanshainClient("http://localhost:8080")
        endpoints = [{"path": "/foo", "method": "GET"}, {"path": "/bar", "method": "POST"}]
        res = client.require_bundle("consumer", "producer", "2.0.1", endpoints)

        self.assertEqual(res["content"], "openapi: 3.0.0")
        _, kwargs = mock_post.call_args
        self.assertEqual(
            kwargs["json"],
            {
                "consumername": "consumer",
                "producername": "producer",
                "version": "2.0.1",
                "endpoints": endpoints,
                "api_type": "openapi",
            },
        )
        self.assertNotIn("timeout", kwargs["json"])
        self.assertNotIn("branch", kwargs["json"])

    @mock.patch("requests.get")
    def test_require_etag_304_not_modified(self, mock_get):
        mock_get.return_value = make_response(304)

        client = SanshainClient("http://localhost:8080")
        res = client.require("consumer", "producer", "1.2.3", "/bar", "GET", etag='"e1"')

        self.assertTrue(res["not_modified"])
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["If-None-Match"], '"e1"')

    @mock.patch("requests.get")
    def test_require_404_unknown_version_message(self, mock_get):
        mock_get.side_effect = [
            make_response(404, {"error": "unknown version"}, text='{"error":"unknown version"}'),
            make_response(200, {"version": "2.0.0"}),  # lazy /version probe: server is fine
        ]

        client = SanshainClient("http://localhost:8080")
        with self.assertRaises(SanshainError) as ctx:
            client.require("consumer", "producer", "9.9.9", "/bar", "GET")

        msg = str(ctx.exception)
        self.assertIn("404", msg)
        self.assertIn("does not exist", msg)
        self.assertIn("GET /producers/producer/versions", msg)

    @mock.patch("requests.get")
    def test_require_410_absent_message_is_distinct(self, mock_get):
        mock_get.side_effect = [
            make_response(410, {"error": "endpoint absent"}, text='{"error":"endpoint absent"}'),
            make_response(200, {"version": "2.0.0"}),
        ]

        client = SanshainClient("http://localhost:8080")
        with self.assertRaises(SanshainError) as ctx:
            client.require("consumer", "producer", "1.0.0", "/bar", "GET")

        msg = str(ctx.exception)
        self.assertIn("410", msg)
        self.assertIn("deliberately", msg)
        self.assertNotIn("404", msg)


class TestWrongServerDiagnosis(unittest.TestCase):
    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_pre_2_server_replaces_confusing_error(self, mock_post, mock_get):
        mock_post.return_value = make_response(422, text="Unknown field: stability")
        mock_get.return_value = make_response(200, {"version": "1.7.2"})

        client = SanshainClient("http://localhost:8080")
        with self.assertRaises(SanshainError) as ctx:
            client.provide("my-service", "openapi: 3.0.0", "snapshot")

        self.assertEqual(
            str(ctx.exception),
            "Sanshain server at http://localhost:8080 is 1.7.2; "
            "this client requires Sanshain 2.x — upgrade the server.",
        )

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_2x_server_keeps_original_error(self, mock_post, mock_get):
        mock_post.return_value = make_response(422, text="wrong shape")
        mock_get.return_value = make_response(200, {"version": "2.1.0"})

        client = SanshainClient("http://localhost:8080")
        with self.assertRaises(SanshainError) as ctx:
            client.provide("my-service", "openapi: 3.0.0", "snapshot")

        self.assertIn("422", str(ctx.exception))
        self.assertIn("wrong shape", str(ctx.exception))

    @mock.patch("requests.get")
    @mock.patch("requests.post")
    def test_unreachable_version_endpoint_keeps_original_error(self, mock_post, mock_get):
        mock_post.return_value = make_response(500, text="boom")
        mock_get.return_value = make_response(404)

        client = SanshainClient("http://localhost:8080")
        with self.assertRaises(SanshainError) as ctx:
            client.provide("my-service", "openapi: 3.0.0", "snapshot")

        self.assertIn("500", str(ctx.exception))
