import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

from sanshainconan.cli import main, resolve_stability, format_version_conflict
from sanshainconan.client import VersionConflictError


class TestResolveStability(unittest.TestCase):
    def test_default_is_snapshot(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_stability(), "snapshot")

    def test_env_switch_sets_ga(self):
        with mock.patch.dict(os.environ, {"SANSHAIN_GA": "true"}, clear=True):
            self.assertEqual(resolve_stability(), "ga")

    def test_env_false_stays_snapshot(self):
        with mock.patch.dict(os.environ, {"SANSHAIN_GA": "false"}, clear=True):
            self.assertEqual(resolve_stability(), "snapshot")

    def test_flag_sets_ga_without_env(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_stability(ga_flag=True), "ga")


class TestFormatVersionConflict(unittest.TestCase):
    def test_openapi_points_at_info_version(self):
        error = VersionConflictError("GA 1.2.0 is immutable", "1.3.0")
        out = format_version_conflict(error, "specs/openapi.yaml", "openapi")
        self.assertIn("GA 1.2.0 is immutable", out)
        self.assertIn("Publish as 1.3.0 — update info.version in specs/openapi.yaml", out)

    def test_proto_points_at_version_marker(self):
        error = VersionConflictError("GA 2.0.0 is immutable", "2.1.0")
        out = format_version_conflict(error, "specs/service.proto", "proto")
        self.assertIn("Publish as 2.1.0 — update the // sanshain-version: marker in specs/service.proto", out)


class TestCliProvide(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.test_dir, "sanshain.yaml")
        with open(self.config_file, "w") as f:
            yaml.dump(
                {
                    "sanshainUrl": "http://localhost:8080",
                    "serviceName": "my-service",
                    "provide": {"file": "api.yaml"},
                },
                f,
            )
        with open(os.path.join(self.test_dir, "api.yaml"), "w") as f:
            f.write("openapi: 3.0.0\ninfo:\n  version: 1.2.0\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _run(self, argv, client):
        with mock.patch("sanshainconan.cli.SanshainClient", return_value=client):
            with mock.patch("sys.argv", ["sanshainconan"] + argv):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    main()
        return out.getvalue()

    def test_provide_defaults_to_snapshot(self):
        client = mock.Mock()
        client.provide.return_value = {"version": "1.2.0", "stability": "snapshot", "changes": {}}

        with mock.patch.dict(os.environ, {}, clear=True):
            out = self._run(["--config", self.config_file, "provide"], client)

        client.provide.assert_called_once()
        args, _ = client.provide.call_args
        self.assertEqual(args[2], "snapshot")
        self.assertIn("Provided 1.2.0 (snapshot)", out)

    def test_provide_ga_flag_wins_over_default(self):
        client = mock.Mock()
        client.provide.return_value = {"version": "1.2.0", "stability": "ga", "changes": {}}

        with mock.patch.dict(os.environ, {}, clear=True):
            self._run(["--config", self.config_file, "--ga", "provide"], client)

        args, _ = client.provide.call_args
        self.assertEqual(args[2], "ga")

    def test_provide_env_switch_sets_ga(self):
        client = mock.Mock()
        client.provide.return_value = {"version": "1.2.0", "stability": "ga", "changes": {}}

        with mock.patch.dict(os.environ, {"SANSHAIN_GA": "true"}, clear=True):
            self._run(["--config", self.config_file, "provide"], client)

        args, _ = client.provide.call_args
        self.assertEqual(args[2], "ga")

    def test_provide_409_surfaces_proposed_version_and_exits(self):
        client = mock.Mock()
        client.provide.side_effect = VersionConflictError("GA 1.2.0 is immutable", "1.3.0")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient", return_value=client):
                with mock.patch("sys.argv", ["sanshainconan", "--config", self.config_file, "provide"]):
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        with self.assertRaises(SystemExit) as ctx:
                            main()

        self.assertEqual(ctx.exception.code, 1)
        printed = out.getvalue()
        self.assertIn("GA 1.2.0 is immutable", printed)
        self.assertIn("Publish as 1.3.0 — update info.version in", printed)


class TestCliRequire(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.test_dir, "sanshain.yaml")
        with open(self.config_file, "w") as f:
            yaml.dump(
                {
                    "sanshainUrl": "http://localhost:8080",
                    "serviceName": "my-service",
                    "requires": [
                        {
                            "serviceName": "other-service",
                            "version": "1.2.0",
                            "outputDirectory": "gen",
                            "endpoints": [{"path": "/foo", "method": "GET"}],
                        }
                    ],
                },
                f,
            )
        self.cwd = os.getcwd()
        os.chdir(self.test_dir)  # keep the .sanshain-cache inside the temp dir

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir)

    def test_require_passes_pinned_version(self):
        client = mock.Mock()
        client.require.return_value = {"not_modified": False, "content": "openapi: 3.0.0", "etag": '"e1"'}

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sanshainconan.cli.SanshainClient", return_value=client):
                with mock.patch("sys.argv", ["sanshainconan", "--config", self.config_file, "require"]):
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        main()

        client.require.assert_called_once()
        args, _ = client.require.call_args
        self.assertEqual(args[0], "my-service")
        self.assertEqual(args[1], "other-service")
        self.assertEqual(args[2], "1.2.0")
        output_file = os.path.join(self.test_dir, "gen", "other-service.yaml")
        self.assertTrue(os.path.exists(output_file))
        with open(output_file) as f:
            self.assertEqual(f.read(), "openapi: 3.0.0")
