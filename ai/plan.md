# SanShain Conan Plugin Plan

## Purpose
The SanShain Conan Plugin provides a way for Conan-based C++ projects to communicate with the SanShain service during the build process to provide or require OpenAPI specifications.

## Core Features
1.  **Provide OpenAPI**: Upload the project's OpenAPI specification to the SanShain service.
2.  **Require OpenAPI**: Download required OpenAPI snippets from the SanShain service for client generation.
3.  **Automatic Branch Detection**: Use Git to detect the current branch automatically.
4.  **Timeout/Retry Mechanism**: Handle asynchronous builds by waiting for requirements to become available.
5.  **Configuration**: Support for `sanshain.yaml` for shared configuration across build tools.

## Implementation Details
-   **Language**: Python (Conan 2.0 extension).
-   **Integration**: Likely implemented as a Conan `python_requires` or a custom command/hook.
-   **Dependencies**: `requests` for HTTP communication, `pyyaml` for YAML parsing, and potentially `GitPython` or standard `subprocess` for Git integration.

## Phases
1.  **Phase 1: Project Setup**: Initialize directory structure and basic documentation. (In progress)
2.  **Phase 2: Core Logic**: Implement the `provide` and `require` functionality in Python.
3.  **Phase 3: Conan Integration**: Integrate with Conan's build lifecycle (e.g., in `layout()` or a custom method).
4.  **Phase 4: Verification**: Add tests to ensure it works with standard Conan workflows.
