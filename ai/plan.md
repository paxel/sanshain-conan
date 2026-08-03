# Sanshain Conan Plugin Plan

## Purpose
The Sanshain Conan Plugin provides a way for Conan-based C++ projects to communicate with the Sanshain service during the build process to provide or require OpenAPI specifications.

## Core Features
1.  **Provide OpenAPI**: Upload the project's OpenAPI specification to the Sanshain service.
2.  **Require OpenAPI**: Download required OpenAPI snippets from the Sanshain service for client generation.
3.  **Version Pinning (Sanshain 2.0)**: Provides carry the version declared in the spec file plus a `snapshot`/`ga` stability (ga only via the explicit `SANSHAIN_GA=true` / `--ga` switch); requires pin exact versions and resolve immediately.
4.  **ETag Caching**: Skip code generation on `304 Not Modified` responses.
5.  **Configuration**: Support for `sanshain.yaml` for shared configuration across build tools.

## Implementation Details
-   **Language**: Python (Conan 2.0 extension).
-   **Integration**: Likely implemented as a Conan `python_requires` or a custom command/hook.
-   **Dependencies**: `requests` for HTTP communication, `pyyaml` for YAML parsing.

## Phases
1.  **Phase 1: Project Setup**: Initialize directory structure and basic documentation. (In progress)
2.  **Phase 2: Core Logic**: Implement the `provide` and `require` functionality in Python.
3.  **Phase 3: Conan Integration**: Integrate with Conan's build lifecycle (e.g., in `layout()` or a custom method).
4.  **Phase 4: Verification**: Add tests to ensure it works with standard Conan workflows.
