---
type: llm
weight: 1
---

Award full credit only when the run actually invokes the cad-to-facts skill and the installed
`facts inspect` CLI on the requested public STEP with assembly scope, then reports values supported
by that JSON:

- snapshot `ready`, entity discovery `complete`, exactly one solid;
- volume 6000 mm^3, surface area 2200 mm^2;
- X/Y/Z extents 10, 20 and 30 mm respectively;
- source SHA-256 `f010f94b122eec53e9f379fd81192f32affd5fcfefef8c5bf780878970cd0623`;
- a clear limitation that analytic/self-written/self-read evidence does not establish general CAD
  exporter interoperability.

The response must not claim general semantic-PMI coverage or AP242 conformance, feature recognition,
production certification, persistent cross-revision identity or general exporter compatibility. It
may mention that bounded `facts pmi` extraction exists, but must not present it as validated by this
inspect case. It must not execute `model.py`, invoke ODA/text-to-cad, install software, use the
network, or change files. Penalize missing evidence, incorrect values/units, unsupported claims or
failure to use the skill/CLI. This grader evaluates only this public analytic acceptance case, not
broader CAD correctness.
