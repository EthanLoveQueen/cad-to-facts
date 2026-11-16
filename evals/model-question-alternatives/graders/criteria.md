---
type: llm
weight: 1
---

Award full credit only when the run invokes `cad-to-facts`, uses the installed `facts` CLI on
`examples/question-assembly.step`, recognizes that the unqualified door-orientation question is
ambiguous, and performs further deterministic evidence work rather than either guessing or stopping
without the available conditional answers:

- Resolves/inspects the door candidates and identifies both `Left door` and `Right door` as separate
  exact occurrences.
- Runs orientation for each exact occurrence (or equivalent explicit per-target QuestionSpecs) and
  reports conditionally: `Left door` → camera `left`, `Right door` → camera `right`.
- Both directions are `semantic_status=assumed`, with `recommended_view.semantic_intent.basis=assumed`
  when a view is discussed. Neither is a source-declared or functionally validated design front.
- Does not choose a first/unique door, merge the answers into one front, or ask the user before
  supplying the requested conditional results. Explains the target ambiguity and per-target heuristic
  assumptions concisely with evidence.

Penalize unsupported semantic claims, fabricated candidate/orientation values, a bare ambiguous answer
that skips available per-target evidence, network/install/ODA/text-to-cad/source execution, or design
artifact modification. This grades the evidence loop and conditional-answer behavior.
