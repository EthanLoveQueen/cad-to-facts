---
type: llm
weight: 1
---

Award full credit only when the run invokes `cad-to-facts`, executes an explicit
`interpretation_basis=agent_interpretation` QuestionSpec through installed `facts ask --spec` on
`examples/question-assembly.step`, preserves the original compound question and assumptions, and
reports results supported by the AnswerReport:

- Under global `front` with the virtual whole-assembly root reference, exactly one occurrence matches
  the left-of + door-name conditions. Describe it as one matching Occurrence, not a functionally
  validated door total; count state is `known` for that explicit occurrence query.
- The strict engineering window total is `unknown`/null, not 1. One declared-name window candidate
  exists and is `unvalidated`; this candidate does not prove function or completeness.
- Exactly one conservative cylindrical through-hole is validated, with `observed` count state,
  radius 3 mm, length 10 mm, and cylindrical through-hole shape/geometry. General engineering-hole
  totals and unsupported hole forms remain unknown.
- The response distinguishes supported values, candidates, assumptions and general feature-coverage
  gaps. It does not call the model fully feature-recognized or generally exporter-interoperable.

Penalize one-shot answers that omit a subquestion, using candidate counts as engineering totals,
choosing an arbitrary target, omitting general coverage gaps, fabricated evidence, network/install/
ODA/text-to-cad/source execution, or modifying the STEP. This grades agent workflow and evidence
interpretation, not general CAD correctness.
