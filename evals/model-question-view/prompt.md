---
max_turns: 20
timeout_seconds: 300
runs: 1
allowed_tools: [Bash, Read, Write, Skill]
---

Use the `cad-to-facts` skill and, for rendering, its `cad-view` handoff on only the public analytic
artifact `examples/question-assembly.step`. Use the installed `facts` CLI. Do not install/update
anything, use the network, invoke ODA or text-to-cad, execute model source, or modify the STEP. Do not
overwrite any existing file.

User request: “请导出左侧门的正面视图，文件名用 `left-door-front.svg`，并简要说明目标、方向假设
和证据文件。”

Resolve the spatial target explicitly, obtain the heuristic recommended view, preserve its semantic
basis, and render one exact occurrence to the requested new SVG in the current work directory. Keep
the sibling view manifest. Verify and report target/camera/semantic assumptions and the artifact/
snapshot binding between resolution and render. If the target or direction is ambiguous, do not guess.
