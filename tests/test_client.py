import pytest
from unittest import mock
from sanshainconan.client import SanshainClient

@mock.patch("requests.post")
def test_provide(mock_post):
    mock_post.return_value.json.return_value = {"status": "ok"}
    mock_post.return_value.status_code = 200
    
    client = SanshainClient("http://localhost:8080", token="test-token")
    res = client.provide("my-service", "main", "openapi: 3.0.0")
    
    assert res == {"status": "ok"}
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["servicename"] == "my-service"
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"

@mock.patch("requests.post")
def test_require_bundle(mock_post):
    mock_post.return_value.text = "openapi: 3.0.0\npaths: /foo: {}"
    mock_post.return_value.status_code = 200
    
    client = SanshainClient("http://localhost:8080")
    endpoints = [{"path": "/foo", "method": "GET"}]
    res = client.require_bundle("client", "service", "main", endpoints)
    
    assert "paths: /foo" in res
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert kwargs["json"]["endpoints"] == endpoints

@mock.patch("requests.get")
def test_require_single(mock_get):
    mock_get.return_value.text = "openapi: 3.0.0\npaths: /bar: {}"
    mock_get.return_value.status_code = 200
    
    client = SanshainClient("http://localhost:8080")
    res = client.require("client", "service", "main", "/bar", "GET")
    
    assert "paths: /bar" in res
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert kwargs["params"]["path"] == "/bar"
