# Java Conformance Runner Scaffold

## Purpose

This package path is reserved for Java conformance runners driven by:

- `sdks/tests/vectors/manifest.yaml`

## Planned Behavior

1. Resolve authoritative public vectors from the manifest.
2. Execute transport/discovery fixture checks against Java runtime behavior.
3. Produce structured output for repository-level conformance reporting.

## Current Status

`implemented (scaffold only)` — directory and ownership are established; runnable suite to be added incrementally.

## Planned Invocation

```bash
mvn -f sdks/java/pom.xml test
```

