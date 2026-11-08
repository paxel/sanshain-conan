"""A failed require in the conanfile helper with bestEffort warns through Conan's output and goes on."""

import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import yaml

from sanshainconan.client import SanshainError
from sanshainconan.integration import Sanshain

# The methods of Conan 2's ConanOutput a recipe's self.output offers; it has
# warning(), no warn().
CONAN_OUTPUT = [
    "debug",
    "verbose",
    "trace",
    "info",
    "status",
    "title",
    "subtitle",
    "highlight",
    "success",
    "warning",
    "error",
]


class TestHelperRequireBestEffort(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)

    def _helper(self, best_effort):
        with open(os.path.join(self.folder, "sanshain.yaml"), "w") as f:
            yaml.dump(
                {
                    "sanshainUrl": "http://localhost:8080",
                    "serviceName": "my-service",
                    "bestEffort": best_effort,
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
        conanfile = SimpleNamespace(
            export_sources_folder=self.folder,
            recipe_folder=self.folder,
            base_folder=self.folder,
            output=mock.Mock(spec=CONAN_OUTPUT),
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            sanshain = Sanshain(conanfile)
        sanshain.client = mock.Mock()
        sanshain.client.require.side_effect = SanshainError("Request failed with status 503: down")
        return sanshain

    def test_best_effort_warns_and_continues(self):
        sanshain = self._helper(best_effort=True)
        sanshain.require()
        output = sanshain.conanfile.output
        output.error.assert_called_once_with(
            "Sanshain: Error requiring other-service: Request failed with status 503: down"
        )
        output.warning.assert_called_once_with("Sanshain: Continuing (best effort)")

    def test_without_best_effort_the_error_is_raised(self):
        sanshain = self._helper(best_effort=False)
        with self.assertRaises(SanshainError):
            sanshain.require()
        sanshain.conanfile.output.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
