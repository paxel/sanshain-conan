import os
from unittest import mock
from sanshainconan.git import get_branch

def test_get_branch_env():
    with mock.patch.dict(os.environ, {"SANSHAIN_BRANCH": "env-branch"}):
        assert get_branch() == "env-branch"

def test_get_branch_github_env():
    with mock.patch.dict(os.environ, {"GITHUB_REF_NAME": "github-branch"}, clear=True):
        assert get_branch() == "github-branch"

def test_get_branch_git_cmd():
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("subprocess.run") as mocked_run:
            mocked_run.return_value.stdout = "git-branch\n"
            assert get_branch() == "git-branch"

def test_get_branch_fallback():
    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch("subprocess.run") as mocked_run:
            mocked_run.side_effect = Exception("git not found")
            assert get_branch() == "main"
