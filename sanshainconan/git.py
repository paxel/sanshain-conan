import os
import subprocess


def get_branch():
    # 1. Check SANSHAIN_BRANCH env var
    val = os.environ.get("SANSHAIN_BRANCH")
    if val:
        return val

    # 2. Check CI environment variables
    ci_branch = _detect_branch_from_ci()
    if ci_branch:
        return ci_branch

    # 3. Try git command
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        branch = result.stdout.strip()
        if branch and branch != "HEAD":
            return branch
        # Detached HEAD — try to resolve
        if branch == "HEAD":
            resolved = _resolve_branch_from_detached_head()
            if resolved:
                return resolved
    except Exception:
        pass

    # 4. Fallback
    return "main"


def _detect_branch_from_ci():
    # GitHub Actions
    ref = os.environ.get("GITHUB_HEAD_REF")
    if ref:
        return ref
    ref = os.environ.get("GITHUB_REF_NAME")
    if ref:
        return ref

    # GitLab CI
    ref = os.environ.get("CI_COMMIT_BRANCH")
    if ref:
        return ref
    ref = os.environ.get("CI_MERGE_REQUEST_SOURCE_BRANCH_NAME")
    if ref:
        return ref

    # Jenkins
    ref = os.environ.get("GIT_BRANCH")
    if ref:
        return ref.removeprefix("origin/")
    ref = os.environ.get("BRANCH_NAME")
    if ref:
        return ref

    # Bitbucket Pipelines
    ref = os.environ.get("BITBUCKET_BRANCH")
    if ref:
        return ref

    # Azure DevOps
    ref = os.environ.get("BUILD_SOURCEBRANCH")
    if ref:
        return ref.removeprefix("refs/heads/")

    # Travis CI
    ref = os.environ.get("TRAVIS_BRANCH")
    if ref:
        return ref

    # CircleCI
    ref = os.environ.get("CIRCLE_BRANCH")
    if ref:
        return ref

    return None


def _resolve_branch_from_detached_head():
    try:
        result = subprocess.run(
            ["git", "branch", "-a", "--contains", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        for raw_line in result.stdout.split("\n"):
            line = raw_line.strip()
            if not line or line.startswith("(") or line.startswith("* ("):
                continue
            if line.startswith("* "):
                line = line[2:]
            if line.startswith("remotes/origin/"):
                candidate = line.removeprefix("remotes/origin/")
                if candidate != "HEAD":
                    return candidate
                continue
            return line
    except Exception:
        pass
    return None
