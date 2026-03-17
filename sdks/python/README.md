# ACP Python SDK (`acp-sdk`)

Reference Python SDK for the Agent Communication Protocol (ACP).

## Install

From source:

```bash
pip install -e .
```

From PyPI (target package name):

```bash
pip install acp-sdk
```

## Included CLI

This package currently ships the `acp` CLI entrypoint (`acp_cli.main:run`) for local workflows.
CLI extraction into a dedicated package is tracked separately in roadmap task `ACP-007`.

## Quick Check

```bash
acp --help
acp --version
```
