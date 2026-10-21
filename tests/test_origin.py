import unittest
from unittest import mock

from sanshainconan.client import SanshainClient, resolve_origin

PROVIDE_OK = {"version": "1.2.0", "stability": "snapshot", "content_hash": "sha256:abc", "changes": {}}


class TestResolveOrigin(unittest.TestCase):
    def test_nothing_known_is_empty(self):
        self.assertEqual(resolve_origin(env={}), {})

    def test_explicit_beats_environment_beats_runner(self):
        env = {
            "SANSHAIN_BUILD_URL": "https://ci/env",
            "SANSHAIN_CHANGE_URL": "https://git/env",
            "SANSHAIN_TICKETS": "ENV-1",
            "SANSHAIN_NOTE": "env",
            "BUILD_URL": "https://jenkins/7",
        }
        self.assertEqual(
            resolve_origin(" https://ci/opt ", "https://git/opt", "A-1, A-2 ,A-1,", " opt ", env=env),
            {"build_url": "https://ci/opt", "change_url": "https://git/opt", "tickets": ["A-1", "A-2"], "note": "opt"},
        )
        self.assertEqual(
            resolve_origin(env=env),
            {"build_url": "https://ci/env", "change_url": "https://git/env", "tickets": ["ENV-1"], "note": "env"},
        )

    def test_runners(self):
        self.assertEqual(
            resolve_origin(
                env={
                    "GITHUB_SERVER_URL": "https://github.com",
                    "GITHUB_REPOSITORY": "acme/orders",
                    "GITHUB_RUN_ID": "123",
                    "GITHUB_REF": "refs/pull/42/merge",
                }
            ),
            {
                "build_url": "https://github.com/acme/orders/actions/runs/123",
                "change_url": "https://github.com/acme/orders/pull/42",
            },
        )
        self.assertEqual(
            resolve_origin(
                env={
                    "CI_JOB_URL": "https://gitlab/acme/orders/-/jobs/7",
                    "CI_MERGE_REQUEST_PROJECT_URL": "https://gitlab/acme/orders",
                    "CI_MERGE_REQUEST_IID": "12",
                }
            ),
            {
                "build_url": "https://gitlab/acme/orders/-/jobs/7",
                "change_url": "https://gitlab/acme/orders/-/merge_requests/12",
            },
        )
        self.assertEqual(
            resolve_origin(env={"BUILD_URL": "https://jenkins/job/7/", "CHANGE_URL": "https://bitbucket/pr/5"}),
            {"build_url": "https://jenkins/job/7/", "change_url": "https://bitbucket/pr/5"},
        )
        self.assertEqual(
            resolve_origin(
                env={
                    "GITHUB_SERVER_URL": "https://github.com",
                    "GITHUB_REPOSITORY": "a/b",
                    "GITHUB_REF": "refs/heads/main",
                }
            ),
            {},
        )


class TestProvideCarriesOrigin(unittest.TestCase):
    @mock.patch("requests.post")
    def test_every_provide_merges_the_origin(self, mock_post):
        resp = mock.Mock(status_code=202, text="", headers={})
        resp.json.return_value = PROVIDE_OK
        mock_post.return_value = resp
        client = SanshainClient("http://localhost:8080")
        origin = {"tickets": ["ORD-7"], "note": "why"}
        for call in (client.provide, client.provide_asyncapi, client.provide_proto):
            call("svc", "x", "snapshot", origin=origin)
            payload = mock_post.call_args[1]["json"]
            self.assertEqual(payload["tickets"], ["ORD-7"])
            self.assertEqual(payload["note"], "why")
            self.assertNotIn("build_url", payload)


if __name__ == "__main__":
    unittest.main()
