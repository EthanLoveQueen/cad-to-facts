# Security policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a public issue for a
suspected vulnerability, and do not attach user production designs, credentials or other secrets.

## Risk model

- STEP, DXF, DWG and other CAD files are untrusted input. Parsers and the underlying geometry
  libraries may fail or behave unexpectedly on malformed content.
- Source scripts referenced by change workflows are executable, untrusted input. They require
  explicit approval and isolation outside this project; the deterministic core does not run them.
- ODA File Converter is optional proprietary software supplied by the user. It is never bundled,
  auto-installed, or discovered from `PATH` by this project.
- The deterministic core is offline. It does not send artifacts, facts or reports to external
  services.
- Outputs are evidence-bound but not a production release, manufacturing approval or independent
  cryptographic attestation.
