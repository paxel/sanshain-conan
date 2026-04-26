import os
import unittest
from unittest import mock
from sanshainconan.git import get_branch


class TestGit(unittest.TestCase):
    def test_get_branch_env(self):
        with mock.patch.dict(os.environ, {"SANSHAIN_BRANCH": "env-branch"}):
            self.assertEqual(get_branch(), "env-branch")

    def test_get_branch_github_env(self):
        with mock.patch.dict(os.environ, {"GITHUB_REF_NAME": "github-branch"}, clear=True):
            self.assertEqual(get_branch(), "github-branch")

    def test_get_branch_git_cmd(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("subprocess.run") as mocked_run:
                mocked_run.return_value.stdout = "git-branch\n"
                self.assertEqual(get_branch(), "git-branch")

    def test_get_branch_fallback(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("subprocess.run") as mocked_run:
                mocked_run.side_effect = Exception("git not found")
                self.assertEqual(get_branch(), "main")
