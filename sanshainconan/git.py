import os
import subprocess

def get_branch():
    # 1. Environment variables (standard for CI)
    for env_var in ["SANSHAIN_BRANCH", "GITHUB_REF_NAME", "CI_COMMIT_REF_NAME", "GIT_BRANCH"]:
        val = os.environ.get(env_var)
        if val:
            return val
            
    # 2. Try git command
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
    except Exception:
        pass
        
    # 3. Fallback
    return "main"
