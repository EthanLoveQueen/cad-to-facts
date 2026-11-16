---
max_turns: 8
timeout_seconds: 180
runs: 1
allowed_tools: [Bash, Read, Skill]
---

Use the `cad-to-facts` skill to inspect only the public analytic artifact
`examples/change-loop/baseline/box.step` with the STEP assembly read scope and a one-entity limit.
Use the installed `facts` CLI; do not install or update anything, use the network, invoke ODA or
text-to-cad, execute the model source, or modify/create any file.

Report concisely:
1. snapshot status, entity discovery and discovered solid count;
2. volume, surface area and X/Y/Z bounding-box extents with units;
3. the full source artifact SHA-256;
4. one interoperability limitation of this analytic/self-read evidence.
