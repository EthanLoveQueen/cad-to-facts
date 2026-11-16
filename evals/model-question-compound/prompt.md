---
max_turns: 18
timeout_seconds: 300
runs: 1
allowed_tools: [Bash, Read, Write, Skill]
---

Use the `cad-to-facts` skill to answer a compound question about only the public analytic artifact
`examples/question-assembly.step`. Use the installed `facts` CLI. Do not install/update anything, use
the network, invoke ODA or text-to-cad, execute model source, or modify the STEP. You may create new
JSON working files in the current work directory, but never overwrite existing files.

User question: “左侧有几扇门？窗户的工程总数是多少？已验证圆柱通孔有几个，半径、长度和形状
是什么？请区分名称候选、已验证结果和仍然未知的范围。”

Decompose the request and use an explicit agent-interpreted QuestionSpec for the compound STEP
questions. Preserve the original question and assumptions. Report concise values with count states,
units, evidence scope and gaps; do not claim that name candidates are functionally validated features.
