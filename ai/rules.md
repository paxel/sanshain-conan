# AI Development Rules for Sanshain Conan

## General Rules
- After every code change, all linters and tests must be executed locally and must be green before any further steps.
- Do not commit or submit changes if any linter (flake8, black, bandit, mypy) reports errors or if tests fail.

## Python Best Practices
- Use `uv` for dependency management and running tools (`uv run ...`).
- Follow PEP 8 style guidelines (enforced by `flake8` and `black`).
- Maintain a maximum line length of 120 characters as configured in `pyproject.toml` and `setup.cfg`.
- Use type hints wherever possible (checked by `mypy`).
- Ensure security best practices are followed (checked by `bandit`):
    - Always provide `timeout` for `requests` calls.
    - Avoid bare `except` blocks; use specific exceptions or `# nosec B110` if justified.
    - Avoid unsafe subprocess calls; use `# nosec` with justification if necessary.

## Conan Development Rules
- Follow Conan 2.x best practices.
- Keep `conanfile.py` clean and well-documented.
- Ensure metadata (license, homepage, topics) is up to date.
- Use `generate()` for preparing build environments and `build()` for actual compilation.
- Include `LICENSE` file in the package via the `package()` method.

## Linter Commands
Run these commands to verify your changes:
```bash
uv run flake8 . --exclude .venv,venv
uv run black --check .
uv run bandit -r . --exclude .venv,venv
uv run mypy . --exclude ".venv|venv"
uv run python -m unittest discover tests
```
