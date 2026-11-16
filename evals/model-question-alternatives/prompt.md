---
max_turns: 20
timeout_seconds: 300
runs: 1
allowed_tools: [Bash, Read, Write, Skill]
---

Use the `cad-to-facts` skill on only the public analytic artifact
`examples/question-assembly.step`. Use the installed `facts` CLI. Do not install/update anything, use
the network, invoke ODA or text-to-cad, execute model source, or modify/create any design artifact.
You may create new JSON working files in the current work directory, but never overwrite existing
files.

User question: “门的正面是哪边？我希望直接得到结果，不要先问我。若有多个合理解释，请分别给出，
但不要替我选择其中一个。”

Start with the ambiguous question, inspect the result, and continue the evidence loop far enough to
provide any independently supported conditional orientation answers. Preserve the exact targets and
assumed-vs-declared semantics. Do not choose a first candidate or invent a unique front.
