# Evidence-guided design questions

Use this workflow for free-form design questions. The agent interprets language and chooses evidence;
the deterministic CLI executes explicit contracts. Keep those roles separate: an interpretation is not
a Fact, a name is not a function, and a successful command is not proof that the user's intended scope
was understood.

This reference covers STEP questions (`locate`, occurrence/feature counts, geometry and assumed
orientation). DWG/DXF questions use the sibling `DrawingQuestionSpec` profile and an explicit
`--spec`; see [Drawing questions](drawings.md#drawing-questions). Do not force entity, layer, block,
text or dimension questions into STEP occurrence fields.

## 1. Decompose before running commands

Translate the request into a small task plan. Identify separately:

- **Subject**: occurrence, declared-name feature candidate, solid, drawing entity, or whole artifact.
- **Intent**: locate, count, geometry, PMI, orientation, review, physical judgment, change, or render.
- **Reference frame**: named reference object, camera, spatial relation and numeric limit, if any.
- **Evidence policy**: strict validated evidence or explicitly requested candidates/assumptions.
- **Deliverable**: a concise answer, neutral JSON, or a new SVG plus manifest.

Split compound requests into separate interpretations. For example, “左侧有几扇门，窗户总数和孔
尺寸是多少，再导出左门正面图” contains occurrence counting, two feature questions, orientation,
and rendering. Do not let a successful first subanswer silently substitute for the others.

Choose the initial evidence path:

| Question kind | Evidence path |
| --- | --- |
| Direct dimension/volume/BOM/PMI lookup | Use the implemented direct command; do not render unnecessarily. |
| Common bounded STEP wording | `facts ask model.step --question "..."` is a useful first probe. |
| Free-form STEP wording with a reviewable interpretation | Write and run an explicit `QuestionSpec` with `--spec`. |
| Compliance judgment | Obtain explicit criteria and run `review`; geometry alone is not a rule verdict. |
| Physical performance or maintenance judgment | State the required analysis, requirements and context; do not infer certification. |
| Explicit occurrence illustration | Resolve one target, then follow `cad-view`. |
| Change intent | Use change preparation; a located candidate is not approval or a persistent target. |

The offline grammar recognizes only bounded door/window/hole locate, count, geometry and assumed-front
forms plus specified directional phrases. `QUESTION_INTERPRETATION_UNSUPPORTED` means the grammar did
not cover the wording, not that the model lacks the object. Use an explicit spec when the interpretation
is defensible; otherwise disclose the unsupported intent. Do not repeatedly rephrase merely to force a
numeric answer.

## 2. Make the interpretation reviewable

For agent-interpreted questions, write JSON with:

- the exact `original_text`;
- `interpretation_basis=agent_interpretation`;
- stable, unique interpretation IDs;
- explicit selectors, feature kinds and evidence policies;
- assumptions introduced by the agent;
- untranslated or unsupported portions in `interpretation_gaps`.

Use multiple interpretation items for independent subquestions. For mutually exclusive readings, use
separately labeled specs or clearly labeled alternative groups in notes; never add counts across
alternative readings. Separate specs are preferable when one aggregate status would obscure which
reading produced which answer.

Example for “左侧门有几个？窗户总数、孔数量和孔尺寸呢？”:

```json
{
  "original_text": "左侧门有几个？窗户总数、孔数量和孔尺寸呢？",
  "interpretation_basis": "agent_interpretation",
  "interpretations": [
    {
      "interpretation_id": "left-door-occurrences",
      "intent": "occurrence_count",
      "selector": {
        "name_contains_any": ["door", "门"],
        "spatial": [{
          "relation": "left_of",
          "reference": {"is_root": true},
          "frame": {"preset": "front"}
        }]
      }
    },
    {
      "interpretation_id": "strict-window-total",
      "intent": "feature_count",
      "feature_kinds": ["window"]
    },
    {
      "interpretation_id": "validated-hole-count",
      "intent": "feature_count",
      "feature_kinds": ["hole"]
    },
    {
      "interpretation_id": "validated-hole-geometry",
      "intent": "feature_geometry",
      "feature_kinds": ["hole"]
    }
  ],
  "assumptions": [
    "Door/window wording is mapped to declared-name aliases, not functional validation",
    "Left uses the global front camera and the whole-assembly root-bbox reference"
  ]
}
```

Run it with `facts ask model.step --spec question.json`. Keep the spec and resulting report available
for the final evidence summary, but do not dump their full JSON when selective fields answer the user.

### Selector and evidence rules

`TargetSelector` ANDs occurrence/definition IDs and names, aliases, root/assembly/state flags and
spatial constraints. Add only constraints justified by the request or disclosed as assumptions. Do not
turn a descriptive adjective into an invented exact name.

Spatial directions compare world-bbox centers in an explicit camera. `near` uses world-bbox gap and
requires `max_distance_mm`; these are not contact, containment or exact shape-distance proofs. An
ordinary reference must be unique. The lone `{"is_root": true}` reference is the virtual whole assembly
formed from root boxes, identified as `assembly:root` in evidence.

Use strict evidence for questions about actual engineering totals. `candidates_allowed` is appropriate
only when candidates are explicitly requested or presented as a separate, conditional evidence layer.
It changes count state and unit; it never validates function. Similarly, an assumed orientation may be
useful for a view but cannot become a declared design front.

## 3. Run an evidence loop, not a single-command loop

After each command, inspect the artifact/snapshot binding, status, completeness/discovery, candidates,
evidence references, diagnostics and gaps. Change the next action only when those results supply a
reason. Do not repeat an unchanged command hoping for a different interpretation.

| Observed result | Next action |
| --- | --- |
| `answered`, `complete=true` | Answer only within the interpretation and evidence policy. Candidate/assumption gaps still matter. |
| `partial` | Report the supported portion, then address a specific actionable gap. General feature coverage may remain unresolved by design. |
| `ambiguous` target | Inspect candidate paths, names, definitions and world boxes with `resolve` or a `locate` interpretation. Narrow only using supplied evidence or a disclosed assumption. |
| Ambiguous orientation with no six candidates | Check target resolution first; an ambiguous target is different from a tied projection axis. |
| Ambiguous orientation with six candidates | Inspect `ORIENTATION_AXIS_AMBIGUOUS` or `ORIENTATION_OUTWARD_DIRECTION_AMBIGUOUS`; do not invent a tiebreaker. |
| `unresolved` | Check selector/unit/discovery evidence and reasonable declared aliases. No discovered match is not proven engineering absence. |
| `unsupported` | Use a reviewable explicit interpretation if possible; otherwise identify the missing contract/capability or required engineering context. |
| `failed` | Read snapshot diagnostics. Keep quantities `unknown`; never turn a failed read into zero. |

Stop the loop when the request is answered within its evidence policy, a decision requires user input,
the remaining gap is an explicit unsupported capability, or no new evidence action changes the result.
Do not manufacture progress by broadening scope silently.

### Ambiguity does not always require an immediate question

If the user wants a unique answer but the evidence supports several conditional answers, preserve the
alternatives. For example, when two doors produce an ambiguous orientation:

1. Run `resolve` with the door selector to recover the actual candidates; an ambiguous
   `OrientationReport` alone does not list them.
2. If the user supplied a discriminating side/path/name, apply it explicitly.
3. Otherwise either ask which target they mean, or—when useful and permitted—run `orient` for each
   exact occurrence and report “left door → assumed left; right door → assumed right.”
4. Do not select the first candidate, merge directions, or claim a unique front.

Conditional answers are useful when they are independently executable and clearly labeled. Ask a
focused question only when the user's next decision requires one alternative. Good clarification topics
are the reference camera, the candidate path, whether candidates are acceptable, and whether an assumed
front is acceptable. Avoid asking for information already present in the report.

## 4. Preserve feature and orientation semantics

Door/window names produce `unvalidated` candidates only. A useful answer to “窗户总数是多少？” may be:

> 严格总数仍未知；发现 1 个声明名称候选，但它不是经过功能验证的窗户，也不能证明没有其他窗户。

Conservative full cylindrical through-holes can be `validated`, but their count is `observed`, not a
complete engineering-hole total. Report radius/length/axis/area only from validated geometry. Blind,
counterbored, rectangular, intersecting and other holes remain outside coverage. Keep
`GENERAL_FEATURE_COUNT_UNKNOWN` and `GENERAL_FEATURE_GEOMETRY_INCOMPLETE` visible in the conclusion.

`facts orient` chooses a unique largest target-bbox projected face pointing outward from the assembly
bbox center. A recommendation is always `semantic_status=assumed`; strict question answers retain
`DESIGN_FRONT_DECLARATION_UNAVAILABLE`. Axis/outward ties return `ambiguous` and no recommendation.

## 5. Hand off views without losing the target

For an SVG deliverable, require one exact active occurrence and a ViewSpecification. Resolve and render
independently re-read STEP, so compare artifact SHA-256 and snapshot IDs before relying on the earlier
selection. Resolve again after a mismatch. Use a new output path; never overwrite the source or an
existing image/manifest.

When using `recommended_view`, preserve `semantic_intent.basis=assumed` and its note. Do not render an
ambiguous target while waiting for a user choice. Follow `cad-view` for camera, output-pair and manifest
checks. SVG is a review/documentation WorkProduct, not exact dimensional evidence.

## 6. Synthesize the answer by evidence class

For a simple question, a compact qualified answer is enough. For compound tasks, organize by subquestion
and make these classes visible:

1. **Supported answer**: value, unit and `known / observed / candidate / unknown` state where relevant.
2. **Evidence scope**: artifact/snapshot, exact target or recognizer method, and relevant spatial frame.
3. **Candidates and alternatives**: preserve ambiguity and conditional results.
4. **Assumptions and gaps**: state what was not validated, inspected or declared.
5. **Deliverables**: new SVG/manifest paths and binding checks, if requested.
6. **Decision needed**: one focused question only if further evidence cannot resolve it.

Prefer precise wording:

- “识别到 1 个已验证圆柱通孔” rather than “模型一共有 1 个孔”；
- “1 个门名称候选” rather than “已确认 1 扇门”；
- “在全局 front 和装配根参考下，左侧条件唯一匹配……” rather than an unqualified “左边就是……”；
- “启发式假设 left 为正面” rather than “设计正面是 left”。

Do not invent numeric confidence. A valid partial, ambiguous or conditional answer is better than a
confident guess. Resolved IDs are snapshot-scoped, not persistent identity or editable-source locations.
VLM inference and PNG/photorealistic rendering are not implemented. Do not upload design files or
derived images without separate authorization.
