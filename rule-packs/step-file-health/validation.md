# STEP file-health pack validation

Scope: the `snapshot.status` checker only. This pack does not validate geometry, semantic PMI,
manufacturing rules, exporter interoperability, or production release.

Public regression seam: `tests/test_review_types.py::test_shipped_file_health_rule_pack_runs_without_custom_authoring`.
The test generates an analytic 10 × 20 × 30 mm STEP box through OCCT, invokes the real `facts review`
CLI with all four files in this pack, and requires:

- process exit 0;
- `overall_status=compliant_for_scope` and `complete=true` for that readable fixture;
- one `file_health` finding and a typed summary;
- source applicability and validation metadata.

The full test suite also exercises failed/partial snapshots and the same `snapshot.status` checker.
Those outcomes are not converted into parser success. External NIST and user production files are not
required to redistribute this pack; the existing corpus suite covers them separately when present.
