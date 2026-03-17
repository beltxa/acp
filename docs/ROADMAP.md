| Task ID | Task Name | Task Description | Completed? |
|--------|----------|----------------|------------|
| ACP-001 | Remove internal artifacts | Remove .venv, .idea, .pytest_cache, .DS_Store, .acp-data from repo and update .gitignore | 100%       |
| ACP-002 | Remove /docs from public repo | Remove all markdown book content from repo; keep only developer-facing docs | 100%       |
| ACP-003 | Create /getting-started | Add minimal developer docs (install, identity, ping example) | 100%       |
| ACP-004 | Restructure repo root | Reorganize folders into sdks/, cli/, relay-dev/, examples/, demos/ | 100%       |
| ACP-005 | Split SDK directories | Ensure each SDK is independently packageable (python, rust, java, etc.) | 100%       |
| ACP-006 | Python SDK packaging | Prepare pip package: acp-sdk with versioning and PyPI readiness | 100%       |
| ACP-007 | CLI packaging | Extract CLI as separate pip package: acp-cli | 100%       |
| ACP-008 | Rust packaging | Prepare Cargo crate (acp) and CLI crate | 100%       |
| ACP-009 | TypeScript packaging | Publish @acp/sdk to npm with proper typings | 100%       |
| ACP-010 | Java packaging | Prepare Maven Central artifact (io.acp:acp-sdk) | 100%       |
| ACP-011 | Go packaging | Prepare go module (github.com/acp/sdk-go) | 100%       |
| ACP-012 | Mojo packaging | Package via pip (temporary) with future native support | 100%       |
| ACP-013 | Create relay-dev boundary | Remove non-public relay capabilities from relay-dev and keep developer relay behavior | 100%       |
| ACP-014 | Define and enforce relay-dev / enterprise boundary (public repo) | Complete when boundary docs are public-safe, relay-dev rejects unsupported out-of-scope config/modes, and tests verify only approved public relay surface | 100%       |
| ACP-015 | Create LICENSE strategy | Apply Apache 2.0 to SDKs + CLI | 100%       |
| ACP-016 | Add README.md | Create high-impact landing page (HTTP for AI agents positioning) | 100%       |
| ACP-017 | Add CONTRIBUTING.md | Define contribution model (initially limited access) | 100%       |
| ACP-018 | Add SECURITY.md | Define vulnerability disclosure process | 100%       |
| ACP-019 | Add ROADMAP.md | Publish this table as official roadmap | 0%         |
| ACP-020 | Create architecture diagram | Add clean SVG diagram showing ACP layers | 100%       |
| ACP-021 | Create quickstart demo | Ensure `pip install + ping` works in <5 minutes | 100%       |
| ACP-022 | Clean examples/ demos | Ensure examples are simple, runnable, and consistent | 100%       |
| ACP-023 | Prepare initial release | Build/package checks completed across SDKs/CLI/relay, and `v0.1.0` tag pushed; publish step blocked pending registry credentials | 90%        |
| ACP-024 | Private repo controls | Restrict write access; allow only trusted collaborators | 100%       |
| ACP-025 | Future: acp-spec repo | Separate protocol spec into its own repo later (tracked in GitHub issue #2 for post-v0.1.0 execution) | 25%        |
