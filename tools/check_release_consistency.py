#!/usr/bin/env python3
"""Check ACP release metadata and public docs stay on one version."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAVEN_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def pyproject_version(path: str) -> str:
    data = tomllib.loads(read(path))
    return data["project"]["version"]


def pyproject_dependencies(path: str) -> list[str]:
    data = tomllib.loads(read(path))
    return list(data["project"].get("dependencies", []))


def cargo_package(path: str) -> dict:
    return tomllib.loads(read(path))["package"]


def cargo_dependencies(path: str) -> dict:
    return tomllib.loads(read(path)).get("dependencies", {})


def json_file(path: str) -> dict:
    return json.loads(read(path))


def maven_text(path: str, xpath: str) -> str | None:
    root = ET.parse(ROOT / path).getroot()
    return root.findtext(xpath, namespaces=MAVEN_NS)


def regex_value(path: str, pattern: str) -> str | None:
    match = re.search(pattern, read(path), flags=re.MULTILINE)
    return match.group(1) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=pyproject_version("sdks/python/pyproject.toml"),
        help="Expected release version. Defaults to the Python runtime version.",
    )
    args = parser.parse_args()
    version = args.version

    checks: list[tuple[str, str | None, str]] = [
        ("sdks/python/pyproject.toml project.version", pyproject_version("sdks/python/pyproject.toml"), version),
        ("sdks/mojo/pyproject.toml project.version", pyproject_version("sdks/mojo/pyproject.toml"), version),
        ("cli/pyproject.toml project.version", pyproject_version("cli/pyproject.toml"), version),
        ("sdks/rust/Cargo.toml package.version", cargo_package("sdks/rust/Cargo.toml")["version"], version),
        ("sdks/rust/cli/Cargo.toml package.version", cargo_package("sdks/rust/cli/Cargo.toml")["version"], version),
        (
            "sdks/rust/cli/Cargo.toml acp-runtime dependency",
            cargo_dependencies("sdks/rust/cli/Cargo.toml")["acp_runtime"]["version"],
            version,
        ),
        ("sdks/java/pom.xml project.version", maven_text("sdks/java/pom.xml", "m:version"), version),
        ("sdks/typescript/package.json version", json_file("sdks/typescript/package.json")["version"], version),
        ("sdks/typescript/package-lock.json version", json_file("sdks/typescript/package-lock.json")["version"], version),
        (
            "sdks/typescript/package-lock.json root package version",
            json_file("sdks/typescript/package-lock.json")["packages"][""]["version"],
            version,
        ),
        ("tools/poker-demo/pom.xml acp.sdk.version", maven_text("tools/poker-demo/pom.xml", "m:properties/m:acp.sdk.version"), version),
        (
            "tools/poker-demo/rust-player/Cargo.toml acp-runtime dependency",
            cargo_dependencies("tools/poker-demo/rust-player/Cargo.toml")["acp-runtime"]["version"],
            version,
        ),
        (
            "tools/poker-demo/go-player/go.mod ACP SDK requirement",
            regex_value("tools/poker-demo/go-player/go.mod", r"require github\.com/beltxa/acp/sdks/go v([^\s]+)"),
            version,
        ),
        (
            "cli/pyproject.toml ACP runtime dependency",
            next((dep for dep in pyproject_dependencies("cli/pyproject.toml") if dep.startswith("acp-runtime>=")), None),
            f"acp-runtime>={version}",
        ),
    ]

    for path in [
        "sdks/python/README.md",
        "sdks/typescript/README.md",
        "sdks/java/README.md",
        "sdks/rust/README.md",
        "sdks/go/README.md",
        "sdks/mojo/README.md",
    ]:
        checks.append((f"{path} header version", regex_value(path, r"version ([0-9]+\.[0-9]+\.[0-9]+)"), version))

    checks.extend(
        [
            ("README.md Python install snippet", regex_value("README.md", r"pip install acp-runtime==([^\s]+)"), version),
            ("README.md CLI install snippet", regex_value("README.md", r"pip install acpctl==([^\s]+)"), version),
            ("README.md TypeScript install snippet", regex_value("README.md", r"npm install acp-runtime@([^\s]+)"), version),
            ("README.md Java Maven snippet", regex_value("README.md", r"<artifactId>acp-runtime</artifactId>\s*<version>([^<]+)</version>"), version),
            ("README.md Rust install snippet", regex_value("README.md", r"cargo add acp-runtime@([^\s]+)"), version),
            ("README.md Go install snippet", regex_value("README.md", r"go get github\.com/beltxa/acp/sdks/go@v([^\s]+)"), version),
            ("sdks/java/README.md Maven groupId", regex_value("sdks/java/README.md", r"<groupId>([^<]+)</groupId>"), "tech.co-operate"),
            ("sdks/java/README.md Maven artifactId", regex_value("sdks/java/README.md", r"<artifactId>([^<]+)</artifactId>"), "acp-runtime"),
            ("sdks/java/README.md Maven version", regex_value("sdks/java/README.md", r"<artifactId>acp-runtime</artifactId>\s*<version>([^<]+)</version>"), version),
        ]
    )

    cli_readme = read("cli/README.md")
    checks.extend(
        [
            ("cli/README.md Rust package table", "Rust (`acp-runtime`)" if "Rust (`acp-runtime`)" in cli_readme else None, "Rust (`acp-runtime`)"),
            (
                "cli/README.md Go package table",
                "Go (`github.com/beltxa/acp/sdks/go`)" if "Go (`github.com/beltxa/acp/sdks/go`)" in cli_readme else None,
                "Go (`github.com/beltxa/acp/sdks/go`)",
            ),
            (
                "cli/README.md Java package table",
                "Java (`tech.co-operate:acp-runtime`)" if "Java (`tech.co-operate:acp-runtime`)" in cli_readme else None,
                "Java (`tech.co-operate:acp-runtime`)",
            ),
        ]
    )

    failures = [(label, actual, expected) for label, actual, expected in checks if actual != expected]
    if failures:
        print(f"Release consistency check failed for {version}:")
        for label, actual, expected in failures:
            print(f"- {label}: expected {expected!r}, found {actual!r}")
        return 1

    print(f"Release consistency check passed for {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
