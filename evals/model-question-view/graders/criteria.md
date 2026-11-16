---
type: llm
weight: 1
---

Award full credit only when the run invokes `cad-to-facts` and the `cad-view` workflow, uses installed
`facts` on `examples/question-assembly.step`, and actually creates both `left-door-front.svg` and
`left-door-front.view.json` as new files without modifying the STEP:

- The target is the unique `Left door` occurrence under global `front` + `left_of` the virtual
  whole-assembly root reference; no first-match or arbitrary target is used.
- The rendered camera is `left`, from the largest-bbox-face outward heuristic. The manifest's
  `semantic_intent.basis` is `assumed`, not user-selected or declared, and the response discloses that
  this is not source-declared/functional-front proof.
- The manifest binds the same source artifact and exact target actually rendered, with SVG output
  hash/size and projected evidence. The response reports both output paths and checks the
  artifact/snapshot binding between independent resolve/orient and render reads, resolving again if
  needed.
- The SVG and manifest exist and are nonempty, and the response does not treat pixels as dimensional
  evidence or claim general visual/geometric equivalence.

Penalize a missing render/manifest, wrong target/camera/semantic basis, overwriting files, unverified
identity claims, network/install/ODA/text-to-cad/source execution, or production-data use. This grades
cross-command target/view orchestration, not general render fidelity.
