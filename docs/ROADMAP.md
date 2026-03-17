| Task ID | Task Name | Task Description | Completed? |
|--------|----------|----------------|------------|
| ACP-001 | Remove internal artifacts | Remove .venv, .idea, .pytest_cache, .DS_Store, .acp-data from repo and update .gitignore | 100%       |
| ACP-002 | Remove /docs from public repo | Remove all markdown book content from repo; keep only developer-facing docs | 100%       |
| ACP-003 | Create /getting-started | Add minimal developer docs (install, identity, ping example) | 0%         |
| ACP-004 | Restructure repo root | Reorganize folders into sdks/, cli/, relay-dev/, examples/, demos/ | 100%       |
| ACP-005 | Split SDK directories | Ensure each SDK is independently packageable (python, rust, java, etc.) | 100%       |
| ACP-006 | Python SDK packaging | Prepare pip package: acp-sdk with versioning and PyPI readiness | 0%         |
| ACP-007 | CLI packaging | Extract CLI as separate pip package: acp-cli | 0%         |
| ACP-008 | Rust packaging | Prepare Cargo crate (acp) and CLI crate | 0%         |
| ACP-009 | TypeScript packaging | Publish @acp/sdk to npm with proper typings | 0%         |
| ACP-010 | Java packaging | Prepare Maven Central artifact (io.acp:acp-sdk) | 0%         |
| ACP-011 | Go packaging | Prepare go module (github.com/acp/sdk-go) | 0%         |
| ACP-012 | Mojo packaging | Package via pip (temporary) with future native support | 0%         |
| ACP-013 | Create relay-dev boundary | Strip enterprise features from relay-dev (no policy engine, no audit pipeline) | 0%         |
| ACP-014 | Define enterprise relay scope | Define private features (federation policies, HA, compliance) | 0%         |
| ACP-015 | Create LICENSE strategy | Apply Apache 2.0 to SDKs + CLI, keep enterprise relay proprietary | 0%         |
| ACP-016 | Add README.md | Create high-impact landing page (HTTP for AI agents positioning) | 100%       |
| ACP-017 | Add CONTRIBUTING.md | Define contribution model (initially limited access) | 100%       |
| ACP-018 | Add SECURITY.md | Define vulnerability disclosure process | 100%       |
| ACP-019 | Add ROADMAP.md | Publish this table as official roadmap | 0%         |
| ACP-020 | Create architecture diagram | Add clean SVG diagram showing ACP layers | 100%       |
| ACP-021 | Create quickstart demo | Ensure `pip install + ping` works in <5 minutes | 0%         |
| ACP-022 | Clean examples/ demos | Ensure examples are simple, runnable, and consistent | 0%         |
| ACP-023 | Prepare initial release | Tag v0.1.0 and publish SDK packages | 0%         |
| ACP-024 | Private repo controls | Restrict write access; allow only trusted collaborators | 0%         |
| ACP-025 | Future: acp-spec repo | Separate protocol spec into its own repo later | 0%         |
