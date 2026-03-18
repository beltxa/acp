# Java Examples

## 1. What The Example Shows

Canonical Java example coverage in this repository:

- `overlay_http_client`: experimental (`examples/java_overlay_spring/`)
- `hello_world`: not yet implemented
- `ping_demo`: not yet implemented
- `send_basic`: not yet implemented
- `send_multi_recipient`: not yet implemented
- `discover_well_known`: experimental (test-backed, no dedicated example file)

## 2. Prerequisites

- JDK 17+
- Maven

```bash
cd sdks/java
mvn test
```

## 3. How To Run

Java overlay example assets currently live under:

```bash
examples/java_overlay_spring/
```

This directory exists to keep canonical scenario naming aligned while Java example packaging is consolidated.

## 4. Expected Behavior

- Java runtime tests validate protocol-level behavior and vectors.
- Overlay sample demonstrates HTTP overlay pattern with ACP semantics.
- Scenario status remains explicit where dedicated SDK examples are pending.

## 5. Related Scenarios

- Taxonomy: `sdks/tests/EXAMPLE_TAXONOMY.md`
- Compatibility view: `sdks/tests/compatibility-matrix.md`
- Canonical interop proof: `demos/canonical_interop/`

