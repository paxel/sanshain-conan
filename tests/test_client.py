import unittest
from unittest import mock
from sanshainconan.client import SanshainClient


class TestSanshainClient(unittest.TestCase):
    @mock.patch("requests.post")
    def test_provide(self, mock_post):
        mock_post.return_value.json.return_value = {"status": "ok"}
        mock_post.return_value.status_code = 200

        client = SanshainClient("http://localhost:8080", token="test-token")
        res = client.provide("my-service", "main", "openapi: 3.0.0")

        self.assertEqual(res, {"status": "ok"})
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["servicename"], "my-service")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-token")

    @mock.patch("requests.post")
    def test_require_bundle(self, mock_post):
        mock_post.return_value.text = "openapi: 3.0.0\npaths: /foo: {}"
        mock_post.return_value.status_code = 200

        client = SanshainClient("http://localhost:8080")
        endpoints = [{"path": "/foo", "method": "GET"}]
        res = client.require_bundle("client", "service", "main", endpoints)

        self.assertIn("paths: /foo", res["content"])
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["endpoints"], endpoints)

    @mock.patch("requests.get")
    def test_require_single(self, mock_get):
        mock_get.return_value.text = "openapi: 3.0.0\npaths: /bar: {}"
        mock_get.return_value.status_code = 200

        client = SanshainClient("http://localhost:8080")
        res = client.require("client", "service", "main", "/bar", "GET")

        self.assertIn("paths: /bar", res["content"])
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["path"], "/bar")
