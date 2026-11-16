# cad-to-facts 详细设计（设计评审稿）

> 状态：编程前设计基线，2026-11-13  
> 上游设计基线：内部维护版本，不随公开仓库发布。  
> 术语以根目录 `GLOSSARY.md` 为准。  
> 本文定义接口、契约、状态与验收语义，不包含实现代码。

## 0. 本文要回答的问题

本文把高层方案展开为可以直接评审和拆分的详细设计，重点回答：

1. 一次读取、审查、修改交接和验证分别接收什么、产生什么。
2. 事实、缺口、诊断和审查结论如何保持不同语义。
3. 文件、快照、实体、规则和修改请求如何绑定版本。
4. 解析失败、单位未知、实体无法匹配时，系统如何保证不误报成功。
5. text-to-cad 的修改基线如何同时关联可编辑源和导出物。
6. BOM 和工艺卡数据在哪里停止，外部系统从哪里接管。
7. P0–P2 在编程前还需要哪些样例、契约和验收用例。

本文首先细化 STEP 单零件审查和 text-to-cad source-backed 修改；装配/BOM 与工艺数据定义公共契约，但不提前展开所有格式细节。

---

## 1. 已确定的设计决策

| 编号 | 决策 | 原因 |
|---|---|---|
| D-01 | 原始 SourceArtifact，包括可编辑源和导出物，永不被覆盖；修改使用 copy-on-write 工作区 | 防止误改和证据漂移 |
| D-02 | Fact 只包含有明确内容的声明、测量或派生结果 | 避免把缺失值当成事实 |
| D-03 | 未获得的数据使用 FactGap，不使用值为 null 的 Fact | 区分“没有”和“没读到” |
| D-04 | Review 同时消费 ModelSnapshot 诊断和 FactSet | 即使解析失败也能进行文件健康审查 |
| D-05 | source-backed 修改分别绑定修改前后的 SourceManifest 和导出物 | 旧 STEP 或旧源单独都不能建立完整来源链 |
| D-06 | 修改执行与验证分开，批准绑定请求和计划哈希 | 防止批准后请求被替换 |
| D-07 | 不承诺跨修订拓扑 ID 稳定；匹配失败即不能通过验证 | 防止改错对象或漏报非目标变化 |
| D-08 | 规则使用声明式配置和命名检查器，不执行模型生成的任意代码 | 可复现、可审核、降低执行风险 |
| D-09 | 默认无数据库、无网络、无 AI 依赖 | 降低部署和隐私成本 |
| D-10 | 下游只输出中立 JSON，不包含外部系统连接器和工艺规划 | 保持项目独立和聚焦 |
| D-11 | 输出几何/规则验证与执行来源证明是两个独立维度 | 外部 handoff 不能证明实际执行了批准计划 |
| D-12 | 每次 Review 显式绑定 ReviewScope、完整 FactSet 和不可变需求来源 | 保证覆盖率和运行身份可计算 |
| D-13 | 模糊目标先形成候选，唯一、歧义、未解析和读取失败分别表示 | 防止按遍历顺序选错对象，防止把未发现当作不存在 |
| D-14 | 模型视图是独立 WorkProduct，几何相机与设计语义方向分开记录 | 防止把图片当 Fact、把全局 front 当成设计正面或从像素读尺寸 |

### 参考环境而非兼容性承诺

高层方案的本机验证环境是 Windows、Python 3.13、cadquery-ocp 8.0.1.1.0。详细实现应首先固定这一参考环境；其他 Python、OCCT 和操作系统组合必须经 CI 和语料验证后再声明支持。

---

## 2. 端到端场景

### S1：单零件需求审查

输入：

- 一个 STEP 文件。
- 一份明确的 Requirement，例如最大外形高度。
- 包含审查阈值和容差的 RuleSet。
- 必要的 ReviewContext。

预期流程：

1. 注册 SourceArtifact 并计算 SHA-256。
2. 读取 ModelSnapshot，记录单位、实体、解析参数和诊断。
3. 提取规则需要的 Fact；无法得到的输入形成 FactGap。
4. 逐条判断适用性并执行检查器。
5. 输出 Finding、总体状态、覆盖率、诊断和证据。

预期结果不是一句“合格/不合格”，而是可复核的 ReviewReport。

### S2：source-backed 修改与复审

输入：

- S1 的一个 violated Finding，或用户明确的修改意图。
- 可编辑 text-to-cad/build123d 源。
- 关联源与导出 STEP 的 SourceManifest。
- 修改后的新导出物。

预期流程：

1. 创建 ChangeRequest，绑定旧 SourceManifest、基线快照/FactSet 和修改前导出物。
2. 检查目标和前置事实，形成完整内容可哈希的 ChangePlan。
3. 用户批准特定请求和计划，形成 ApprovalRecord。
4. 在 copy-on-write 工作区修改源副本，由 text-to-cad 产生新源和新导出物。
5. 形成新 SourceManifest，关联新源、构建配置和新导出物；记录 ExecutionRecord。
6. 注册并解析新文件，用固定 profile 执行验收、保持项检查和必要的原规则复审。
7. 输出 ModificationReport，分别给出结果验证状态和执行来源状态；缺少执行记录时明确为 unattested，不声称批准计划已被证明执行。

### S3：模型 BOM 数据提取

输入为 STEP 装配，输出零件定义、活动实例、数量、已声明属性和缺失字段。若实例状态、外部引用或装配关系无法完整解析，BOMExtract 必须标记不完整，不能按已成功遍历的 solids 数量给出确定总 BOM。

### S4：工艺卡输入准备

输入为单零件及可选的显式任务上下文，输出几何、PMI、检验对象、特征候选和缺失输入。不生成工序顺序、装夹方案、设备/刀具选择或加工参数。

### S5：模糊目标解析与技术视图导出

用户说“导出门的正面图”时，先把功能指代与观察方向分开。`ask --question` 提供受限中英文
语法，agent 也可把任意问题解释成显式 QuestionSpec；两者都保留原文、假设和解释缺口，并走
同一 AnswerReport 执行器。名称候选不证明门的功能，多个候选必须保留歧义。`resolve` 支持声明
字段及显式相机/参考对象下的世界包围盒空间关系。`features` 只验证保守圆柱通孔，门窗名称仍是
未验证候选。`orient` 以最大包围盒投影面和相对装配中心向外生成假设正面，轴向或外向歧义时不
推荐方向。选定活动 Occurrence 后，`render` 按 ViewSpecification 生成新 SVG 和来源清单。图片
不能提供精确尺寸，也不能自动成为修改目标、持久身份或源码行号。图纸问答使用独立的
DrawingQuestionSpec 与实体/图层/块/文字/测量/尺寸意图，不复用 STEP Occurrence 语义；它只回答
有界图纸事实，不做通用图纸语义理解。通用自然语言理解、通用特征识别、源声明/功能正面识别和
VLM 仍未实现。

agent 工作流位于 skill 而非几何核心：先分解主体、意图、参考系、证据策略和交付物，再生成显式
解释，根据 AnswerReport 状态和缺口选择下一证据动作。目标歧义可通过对每个精确 Occurrence 的
条件回答保留，不得在互斥解释之间累加数量；只有决策必须由用户选择时才追问。复合回答按已支持
数值、候选、假设和缺口组织，视图交接必须继续保持 artifact/snapshot/target 绑定。公开
`examples/question-assembly.step` 和 `evals/model-question-*` 固定该行为的本地评测输入。

---

## 3. 模块划分与依赖方向

```text
CLI / SKILL 编排
       │
       ▼
Artifact ──→ Snapshot ──→ Facts ──→ Review
                              │         │
                              │         └─→ Change preparation
                              │                │
                              │                ├─→ text-to-cad handoff
                              │                └─→ Change verification
                              │
                              ├─→ BOM extraction
                              └─→ Process-card input preparation
```

依赖方向必须保持单向：

- domain 不 import 具体 OCCT、cadtokens 或 text-to-cad 实现。
- adapters 依赖 domain 契约，不允许 domain 反向依赖 adapters。
- review 不直接调用 OCCT；需要的几何数据通过 Facts 接口取得。
- change verification 复用 Snapshot、Facts 和 Review，不另写一套数值计算。
- downstream 不读取 ERP/CAPP，也不修改 SourceArtifact。

### 模块接口总表

| 模块 | 接口 | 关键不变量 |
|---|---|---|
| Artifact | `register(path) -> SourceArtifact` | 只读源字节；哈希来自原始内容 |
| Snapshot | `read(artifact, options) -> ModelSnapshot` | 失败也返回可诊断快照；不静默修复 |
| Facts | `extract(snapshot, query) -> FactSet` | 值进入 facts，缺失进入 gaps |
| Review | `review(ReviewRequest) -> ReviewReport` | 固定完整输入；不适用、未知和违规具有不同语义 |
| Change | `prepare / plan / verify(VerificationRequest)` | 执行前必须验证版本和批准；输出验证与执行来源分开 |
| BOM | `extract(snapshot, options) -> BOMExtract` | 数量来自实例；不完整发现必须公开 |
| Process data | `prepare(snapshot, facts, context) -> ProcessCardInput` | 不包含工艺规划决策 |
| Target resolution | `resolve_target(snapshot, selector) -> TargetResolution` | 声明/空间候选不自动消歧，世界放置与发现完整性保留 |
| Features | `recognize_features(snapshot, query) -> FeatureRecognitionReport` | 名称候选与已验证几何分离，通用覆盖保持 unknown |
| Orientation | `infer_orientation(snapshot, selector, policy) -> OrientationReport` | 启发式方向必须可复算，歧义不推荐，语义仅为 assumed |
| Questions | `answer_question(snapshot, spec) -> AnswerReport` | 解释、证据、假设、计数状态与缺口分离 |

这些接口是测试面。测试应通过同一接口使用真实适配器和可控的内存替身，而不是绕过接口直接测内部辅助函数。

---

## 4. 标识、哈希与不可变对象

结构化对象的内容哈希统一使用 UTF-8 的 RFC 8785 JSON Canonicalization Scheme，并加入域分隔：

```text
SHA-256("cad-to-facts:<object-type>:<schema-version>\0" || canonical_json_bytes)
```

数组是否排序由各自 schema 决定：语义无序的集合先按稳定键排序，顺序有意义的装配路径、操作和引用列表不得排序。被哈希对象包含全部语义字段，只排除明确列出的非语义展示字段，如生成时间和展示用绝对路径。路径一旦构成输出位置、批准范围或安全策略等语义约束，就必须以规范化形式参与哈希，不能因字段类型是绝对路径而排除。SourceArtifact 继续使用原始字节哈希，不使用 JSON 规范化。

### 4.1 SourceArtifact

必需字段：

| 字段 | 语义 |
|---|---|
| `sha256` | 原始文件字节哈希 |
| `size_bytes` | 文件大小 |
| `format` | 探测结果；无法确定时明确为 unknown |
| `format_schema` | 如 AP242；无法取得时为缺失 |
| `source_locator` | 展示用路径或外部标识，不参与内容身份 |
| `design_revision` | 可选业务版本，不参与内容身份 |

注册前后如文件内容发生变化，应返回新的 SourceArtifact；任何后续操作都使用注册时哈希作为前置条件。读取过程中发生内容变化时，本次快照必须失败并提示重新注册，不能混合两次读取的数据。

### 4.2 SourceManifest

source-backed 修改在修改前后各需一份 SourceManifest，至少包含：

- `sources[]`：可编辑脚本/模型的 SourceArtifact 哈希。
- `parameters`：规范化后的构建参数及其内容哈希。
- `dependency_lock`：依赖锁定文件或等价配置的内容哈希。
- `generator`：text-to-cad/构建器名称与版本。
- `outputs[]`：生成物哈希及其与源的对应关系。
- `lineage_kind=root / derived`：区分首次构建和由既有版本修改而来。
- `parent_manifest_sha256`：仅 derived 必填，指向修改前清单；root 必须省略该字段。
- `modified_from[]`：仅 derived 使用，记录 `{old_path, new_path}`；root 必须省略。验证器按前后 ManifestFile 的实际哈希确定同源路径是否改变，并要求声明映射精确覆盖这些变化，不能把已改源伪装成空映射 no-op。新增或删除源由完整 sources 集合并对照 ChangePlan 识别。
- `manifest_sha256`：上述完整规范化内容的哈希。

旧清单必须包含 base_artifact，新清单必须包含待验证的新导出物。完整 source-backed 来源链要求报告引用两份清单；缺少新清单时，只能进行输出结果验证，不能声称建立了 source-backed 来源链。不得为 root 清单编造 parent 或旧源，也不得用 null 代替上述明确的 root/derived 结构。

SourceManifest 只证明“这组源和配置声明对应这些输出”。首次使用前仍需一次实际构建或可信来源验证，不能仅凭清单文字认定导出物确实由该源生成。

### 4.3 ModelSnapshot

`snapshot_id` 是“源 + 读取配置”的身份，由以下内容规范化后计算：

```text
artifact.sha256
+ adapter id/version
+ parser/kernel version
+ canonical parse options and requested read scope
```

另有 `snapshot_content_hash`，对包括实体、诊断和覆盖信息在内的完整快照内容计算。ReviewRun 同时绑定 snapshot_id 和 snapshot_content_hash，防止相同配置下变化的部分解析结果复用运行身份。

快照状态由诊断和发现状态确定，而非适配器自由判断。`unresolved` 统一定义为 `disposition != resolved`，因此 open 和 accepted 都仍未解决：

| 状态 | 判定 |
|---|---|
| `failed` | 影响请求范围的 unresolved 致命诊断导致无法建立模型；仍保留文件健康诊断 |
| `partial` | 获得部分内容，但请求范围内存在 `impact=partial/fatal` 的 unresolved 诊断，或实体发现不是 complete |
| `ready` | 请求读取范围内发现完整，且没有影响该范围、`impact=partial/fatal` 的 unresolved 诊断 |

`impact=none` 的信息、警告或错误不阻止 ready，因为它声明不影响本次范围；适配器不能利用这一点隐瞒实际影响。诊断的影响范围、open/resolved/accepted 状态在 §5.1 定义。accepted 只表示人工知悉，不删除诊断、不使其变为 resolved，也不能把实体发现不完整改成 complete。只有带复核证据的 resolved 才不再驱动 partial/failed。

`ready` 不代表 CAD 几何有效，也不代表文件包含所有设计语义，只代表本次解析范围完成。

### 4.4 EntityRef

包含：

- `snapshot_id`
- `entity_id`
- `entity_kind`
- `native_refs[]`：类型和值，例如 STEP entity、DXF handle、IFC GlobalId
- `assembly_path[]`：适用时保留实例路径
- `adapter_key`：没有源生标识时的确定性遍历键

`entity_id` 只保证当前快照内唯一；所有 EntityRef 都设置 `identity_scope=snapshot`。native_refs 和源操作映射只是后续跨修订匹配的证据，不会把 EntityRef 本身升级为持久标识。

### 4.5 派生文档 ID

- Fact ID：对完整 Fact 内容计算，包括快照、主体、谓词、值、方法/库版本、提取器版本和参数；任何语义变化都产生新 ID。
- FactSet ID：对完整 facts、gaps、diagnostics、提取查询、提取器版本和 schema 版本计算。
- ReviewRun ID：对 snapshot_id、snapshot_content_hash、FactSet ID、含不可变需求引用的 RuleSet、ReviewScope、ReviewContext 和 Reviewer 版本计算。
- Finding ID：由 ReviewRun、Rule 和主体计算，不把当前状态混入 ID；报告另有完整内容哈希。
- ChangeRequest ID：对完整规范化请求内容计算，包括基线快照/FactSet 和验证 profile。
- ChangePlan ID：对完整规范化计划内容计算，包括目标绑定、操作、受控载荷、比较方法、容差、预期失效和 manifest 检查结果。
- ApprovalRecord、ExecutionRecord 和 ModificationReport 也使用各自完整规范化内容的哈希；终端报告不可原地修改，重试验证创建新报告并引用原报告。

纯展示时间戳、随机 UUID、日志顺序和纯展示用绝对路径不进入上述哈希。ApprovalRecord.approved_at 和 ExecutionRecord.executed_at 是批准/执行声明的语义内容，当前实现将其纳入各自内容 ID，不能在不改变记录身份的情况下改写。语义输出位置和其他影响行为的路径必须进入相应对象哈希；确定性测试只排除 schema 明确标记为非语义的展示字段。

语义无序的集合在哈希前先规范化排序：Requirement 按 `requirement_id`，Rule 按 `(rule_id, version)`，Rule 的 `requirement_refs`，ReviewScope 的规则引用/选择器/必需输入/发现要求，以及 FactSet 的 facts/gaps/query requests。仅改变这些集合的顺序不得改变任何内容 ID。

Reviewer 在评估前重算并校验 `snapshot_content_hash`、每个 Requirement 的 `content_hash`、`bundle_id`、`ruleset_id`、`scope_id`、`context_id`、每个 `fact_id` 和 `factset_id`。声明的内容 ID 与实际内容不符属于配置错误（CLI exit 2），不得按 finding 处理，也不得用调用方提供的 ID 冒充已绑定内容。RuleSet 可同时包含同一 `rule_id` 的多个 `version`；`ReviewScope.included_rules` 既可写规则 ID 字符串（仅当该 ID 只有一个版本时），也可写 `{rule_id, version}` 明确选择版本。字符串引用多版本规则、引用未知版本或重复选择同一版本均为配置错误。

---

## 5. 核心数据契约

### 5.1 Diagnostic

统一诊断结构至少包含：

| 字段 | 说明 |
|---|---|
| `code` | 稳定机器码，如 `UNIT_UNKNOWN`、`ENTITY_SKIPPED` |
| `severity` | info / warning / error / fatal |
| `stage` | probe / read / translate / measure / review / change |
| `message` | 人类可读说明 |
| `scope_refs` | 受影响的读取范围、能力或实体；空值不表示全局影响 |
| `affects` | discovery / geometry / pmi / metadata 等受影响能力 |
| `impact` | none / partial / fatal，描述对声明范围的影响 |
| `discovery_impact` | none / partial / unknown，单独驱动发现完整性 |
| `disposition` | open / resolved / accepted；accepted 必须包含理由和上下文来源 |
| `entity_refs` | 已知的关联实体 |
| `count` | 同类对象数量；未知时省略并另加说明 |
| `details` | 解析器特定补充，不替代公共字段 |

适配器必须按诊断代码和请求范围给出上述字段，不能临时判断“这个错误是否重要”。resolved 表示原因已消失且有复核证据；accepted 表示用户在本次上下文中知悉，不等于 resolved。影响发现完整性的诊断会驱动 ModelSnapshot 和 ReviewReport 的 incomplete/partial 状态。

空实体数组只在确定“没有相关实体”时使用；无法确定时使用相应 FactGap 或诊断。

### 5.2 FactSet

FactSet 同时包含：

- `facts[]`：实际取得的 Fact。
- `gaps[]`：未获得或不完整的 FactGap。
- `diagnostics[]`：提取过程诊断。
- `snapshot_id`：所有内容的来源快照。
- `extraction_query` / `extractor_version`：本次提取的完整请求和实现版本。
- `factset_id`：对上述全部内容及 schema 版本计算的完整内容哈希。

Fact 必需字段：

| 字段 | 说明 |
|---|---|
| `kind` | declared / measured / derived |
| `subject` | EntityRef 或快照级主体 |
| `predicate` | 稳定谓词，如 `volume`、`bbox.extent.z` |
| `value` | 实际值 |
| `unit` | 数值物理单位；无单位值明确为 dimensionless |
| `evidence` | 文件与源生实体证据 |
| `method` | 库、算法、版本、参数 |

FactGap 必需字段：

- `request`：原本尝试获得什么。
- `subject`：已知时填写。
- `reason_code`：如 `ABSENT`、`UNKNOWN_UNIT`、`UNSUPPORTED`、`PARSE_FAILED`、`MEASUREMENT_FAILED`、`NOT_COMPUTED`。
- `blocking_capabilities`：下游因此不能完成什么。
- `evidence`：支持“声明缺失”或“解析失败”的来源信息。

`ABSENT` 只能在格式和解析覆盖允许证明不存在时使用；普通搜索无结果不能使用它。若一次规则输入查询既没有产生 Fact 也没有产生 FactGap，Reviewer 必须补建 `NOT_COMPUTED` FactGap，并按 unknown 处理，不能把遗漏当作 ABSENT。OCCT 测量异常、负值或非有限物理结果使用 `MEASUREMENT_FAILED`，按请求隔离，不能中断其他独立测量或输出无效 Fact。

### 5.3 数值与单位

- 对外数值使用 `{value, unit}` 语义，不以 `_mm` 字段名暗示所有输入都是毫米。
- 保留原始声明单位；如归一化到另一单位，同时记录原值、转换因子和目标单位。解析器不暴露换算前坐标时，可以记录明确标注为“派生”的源值（系统值除以因子），不得把它冒充为独立解析或测量结果。
- 网格或无单位 DXF 不得默认毫米。
- 当前 STEP 已验证的长度单位是 mm、cm 和 in；其他单一声明单位保留实体和单位，但快照为 partial，长度事实返回 `UNKNOWN_UNIT`，不得猜测换算。当前 drawing profile 另行验证 mm、cm、m、in 和 ft，并按 `$INSUNITS` 将支持的数值事实归一化为 mm/mm²；unitless 不默认毫米。
- 角度、面积、体积、长度使用不同单位维度，不能只传单位字符串而不校验维度。
- 浮点比较必须带绝对或相对容差；容差来自规则、解析精度或明确的比较策略。

### 5.4 装配基础模型

公共模型还包含 `AssemblyLink`（父子 Occurrence 关系）和 `AssemblyStructure`（根、定义、实例、链接、发现状态和源记录计数）。当前 `read_scope=assembly` 已通过 STEPCAFControl_Reader/XCAF 实现这些概念；Occurrence 保留局部行优先 4×4 变换和路径，但不能把快照内 ID 当作持久零件号。

- `PartDefinition`：可复用的零件定义。
- `Occurrence`：装配中的一次实例，引用 PartDefinition 并带有变换和状态。

不能把同一个 PartDefinition 的多个 Occurrence 合并成多个独立零件，也不能只按名称关联。

`read_scope=single_part` 读取 STEP 时先检查 `NEXT_ASSEMBLY_USAGE_OCCURRENCE`。存在装配记录时仍可测量扁平化后的 solids，但必须记录 `source_structure=assembly_flattened`、设置 `entity_discovery=partial` 并产生 `ASSEMBLY_STRUCTURE_NOT_REPRESENTED`；`assembly_path` 为空不得被解释为“无装配层级”。装配 profile 额外对账源 PRODUCT/NAUO 数与 XCAF 定义/组件数，不一致时结构发现为 partial，禁止完整 BOM 声明。

### 5.5 Drawing profile 与转换证据

DWG/DXF 使用独立的 `DrawingStructure`，不把图元映射为 STEP solids，也不复用 B-rep 的 volume/BOM 语义。DXF 通过 ezdxf recovery/audit 直接读取；DWG 的主 SourceArtifact 始终是原文件，由单独安装的 ODA File Converter 在新的临时输入/输出目录中本地生成 ACAD2018 DXF，再进入同一 ezdxf 路径。不得覆盖源文件、通过 shell 拼接命令或默认上传文件。没有 ODA 时返回 failed/unknown 与 `ADAPTER_UNAVAILABLE`，不是解析成功。

`DrawingConversion` 记录 ODA 可执行文件 SHA-256、固定输出格式/版本、audit 选项和派生 DXF SHA-256/大小。它只绑定本次转换证据；可执行文件哈希不覆盖所有 DLL，转换也不证明视觉或语义等价。运行配置中的可执行文件路径不进入快照内容身份。

当前目录覆盖 model/paper-space layouts、非 layout blocks、layers 和实体的 DXF type/handle/container/layer/source artifact/unit。普通块引用不展开成重复几何；块引用上附着的 ATTRIB 值在引用容器下登记一次，ATTDEF 仍属于其块定义。外部引用默认不解析并产生 `DRAWING_EXTERNAL_REFERENCE`；audit errors/fixes 和空实体目录阻止不恰当的完整声明。声明事实包括 `entity_type/layer/container`，适用时包括 `text/attribute_tag/block_name`；数值事实仅覆盖 LINE、ARC、CIRCLE 和 LWPOLYLINE 的明确长度/面积/圆周算法。LWPOLYLINE bulge 使用 `theta=4*atan(b)`、弦长半径和带符号圆缺面积的解析公式，不得用直线段近似。其他未实现测量返回 `UNSUPPORTED`。宿主 DWG 数值方法参数带派生 DXF 哈希；展平 XREF 实体必须绑定实际子 artifact 的哈希、单位和派生 DXF 哈希，不得继承宿主证据。

XREF 有 `unresolved / linked / flatten` 三种模式。`linked` 在 `DrawingStructure.external_references` 中以平铺边记录 owner/reference artifact、嵌套父引用、解析状态、单位、实体与发现计数和诊断，不把子实体混入宿主目录。`flatten` 仅在内存中嵌入引用块内容，并通过内部 provenance 标记保留真实来源；普通 INSERT 仍不展开成重复几何。只有显式 `xref_roots` 下的本地文件可读取，绝对路径也必须位于根内；UNC、URL、网络位置、越界相对路径、循环、超限和缺失输入均保持 partial。默认深度/文件数/总字节/时间预算分别为 8、64、256 MiB、120 秒；进程内解析的超时只能协作检查，不能宣称为抢占式沙箱。

### 5.6 图纸选择性输出、渲染与属性 BOM

`inspect --summary` 返回结构计数而不返回实体目录/FactSet；`query` 以 entity kind、layer、container 和文本子串筛选并按 snapshot 内游标分页，只返回选中 EntityRef 与事实。过滤值在单字段内取 OR、字段间取 AND；游标不承诺跨 snapshot 有效，页大小必须为正数，拒绝零/负 limit 而不是返回无法推进的游标。它们限制输出而非初始解析成本。

`render` 使用 ezdxf SVG backend 为一个布局生成新的 SVG，采用独占创建且不覆盖任何已有文件。外部栅格图像由 `ImagePolicy.IGNORE` 忽略，渲染不得隐式读取其引用文件；全部被忽略时仍可产生空审查 SVG。SVG 只是审查用 WorkProduct，字体/SHX 替代、渲染后端和布局差异使其不能证明视觉或几何等价。linked 模式只渲染宿主布局；需要合成引用块的派生视图时必须显式 flatten。

`DrawingBOMExtract` 与 STEP `BOMExtract` 分离。`drawing-bom` 必须显式给出 part tag，数量/材料/描述和必需属性也由调用方指定；默认只处理 Model 中 INSERT/MINSERT。未指定 quantity tag 时按实例计数并包含 MINSERT 行列重数；非正实例数或对应零间距的歧义阵列使数量 unknown。指定后只接受规范正整数，缺失、冲突或非法值使数量为 unknown，禁止回退猜测。行按声明零件号分组，保留块名、出现引用、属性冲突及全部来源 artifact 哈希。XREF 附着 INSERT 本身不是零件出现；linked 内容不隐式计数，flatten 子实体必须经显式 container 选择。未计数的 XREF 默认阻止完整，`--allow-xref-exclusion` 仅在明确接受所选范围排除它们时解除该项阻止，并在 options/诊断中保留证据，不表示已统计被排除内容。只有结构发现完整、必需属性无缺失、数量和身份无 unknown 时才可 `complete=true`。该输出不是 ACAD_TABLE 解析、标题栏推断、制造 BOM 或 ERP 主数据。

### 5.7 STEP 目标解析、特征、方向、问答与模型视图

`TargetSelector` 以 AND 组合 Occurrence ID、ID 路径、名称/名称子串/别名、定义 ID、根节点、
装配类型、实例状态及空间约束。名称匹配同时检查 Occurrence 和 PartDefinition 声明名，但结果
分别保留二者。`TargetResolution` 区分 `resolved / ambiguous / unresolved / failed`，不得按
遍历顺序选择。`complete` 只表示结构发现完整且所有返回候选都有世界包围盒，不是功能识别或
完整形状验证。

空间关系必须给出显式相机和非嵌套参考 selector。左右/前后/上下比较世界包围盒中心在相机轴上
的投影；near 必须给出 `max_distance_mm`，使用世界包围盒间隙。普通参考必须唯一，单独
`{"is_root": true}` 参考表示由全部根 Occurrence 包围盒并集构成的虚拟装配整体，不任选一个根。
这些关系不证明接触、包含或精确形状距离。证据保留参考 ID、相机、坐标或距离和计算方法。

`FeatureRecognitionReport` 把 door/window 声明名称候选标为 unvalidated，把满足完整内圆柱、两个
圆形开放端边、平面端面、轴平行及面积一致条件的孔标为 validated。普通圆柱实体不是孔；盲孔、
沉孔、矩形孔、槽和复杂相交孔不在验证覆盖内。`general_feature_coverage=unknown` 永久保留，
bounded `complete` 不表示全部工程特征已识别。

`OrientationReport` 对唯一目标输出六个全局相机候选的投影面积、深度和中心偏移。只有最大投影
轴唯一且目标中心相对装配根包围盒中心的外向符号唯一时才给出 `recommended_view`。该视图
`semantic_intent.basis=assumed`，不是源声明或功能正面；相近轴面积或近零偏移必须返回 ambiguous。

`QuestionSpec` 保存原文、deterministic_grammar/agent_interpretation/user_supplied 来源、多解释、
假设和解释缺口。`AnswerReport` 对 locate、occurrence_count、feature_count、feature_geometry 和
orientation 共用同一执行器，分离 TargetResolution、FeatureRecognitionReport、OrientationReport、
计数、几何和 AnswerGap。strict 特征计数只报告 observed 的已验证孔并保留通用缺口，门窗总数保持
unknown；candidates_allowed 只把计数标为 candidate。假设正面保留
`DESIGN_FRONT_DECLARATION_UNAVAILABLE`。`complete=true` 仅表示所有显式解释均 answered，不表示
通用语义或特征覆盖完整。

`ask --spec` 与 `--question` 互斥。后者只支持受限中英文门窗孔定位、计数、几何和假设正面语法；
不支持的问题返回 unsupported。未显式指定空间参考时，语法使用全局 front 相机和虚拟装配根，
并记录假设；自然语言 near 没有数值距离时不得猜测。任意自然语言可由 agent 转成显式 spec，
但解释不能进入 FactSet。完整契约见 `docs/model-questions.md`。

DWG/DXF 使用独立的 `DrawingQuestionSpec` / `DrawingAnswerReport` 兄弟 profile，不把 entity、
layer、block、text、dimension 硬套进 STEP Occurrence/TargetSelector。图纸意图包括实体计数/查找、
文字查找、图层/块清单、长度/面积/周长汇总、声明尺寸清单、名称候选计数、声明语义证据包和显式属性
BOM 查询。语义证据按块名、图层名、文字和属性 tag 匹配，并带出 INSERT 附着的 ATTRIB 声明值，但固定
`validation=unvalidated`，不是推断出的材料/零件/功能字段。计数区分 known/partial/unknown/candidate：
只有实体发现完整时 catalog 计数为 known；XREF 未解析或恢复不完整时为 partial；读取失败或发现未知时
value=null，绝不把失败读成 0。省略容器表示整个 catalog（含模型空间、图纸空间和块定义），必须显式
披露，不能当作图纸的语义总数。块清单区分定义与 INSERT/MINSERT 实例且不展开几何；尺寸值不关联其所
标注的几何；名称候选固定 `validation=unvalidated` 和 `general_semantic_coverage=unknown`。图纸自然
语言语法未实现，图纸问题必须由 agent 生成显式 spec；通用图纸语义理解、标题栏推断和功能特征验证仍
未实现。完整契约见 `docs/drawing-questions.md`。

STEP `render` 只接受一个活动 Occurrence 和显式 ViewSpecification，通过 OCCT 隐藏线投影生成新 SVG 与
`.view.json` 清单。相机预设仅表示全局坐标方向；清单绑定 artifact/snapshot/target、完整视图参数、
内核和方法、投影统计、诊断及图片字节哈希。两个输出均独占创建，不覆盖既有文件。SVG 是
WorkProduct，不是 Fact、视觉/几何等价证明或像素测量来源。完整字段见 `docs/model-views.md`。

面/边选择器、通用特征识别、源声明/功能正面识别、PNG/照片级渲染和 VLM 问答仍未实现。未来视觉
解释只能作为独立 Inference，不能进入 FactSet 或覆盖确定性证据。

---

## 6. 审查详细设计

### 6.1 输入对象

一次 ReviewRun 由一个完整 ReviewRequest 固定以下输入：

```text
ModelSnapshot（包括 snapshot_content_hash 和诊断）
FactSet（包括完整 factset_id、FactGap 和提取版本）
RuleSet（包括规则实现版本、内容哈希和不可变 RequirementBundle）
ReviewScope（包括对象选择条件、规则子集、必需输入和发现要求；不含实际候选清单）
ReviewContext（包括显式用户输入）
Reviewer 版本
```

RuleSet 内的每个 Requirement 都包含 ID、原文、来源引用和内容哈希；外部来源另带 SourceArtifact 哈希或明确的不可变来源版本（当前实现以可选的 `Requirement.source_sha256` 承载外部字节哈希）。Rule 的 requirement_refs 必须解析到这些具体内容，不能只保留可能变化的文档名称。

上述任一输入变化都产生新的 ReviewRun ID。报告记录完整输入引用，不能只保存规则名称。模块接口可简写为 `review(ReviewRequest) -> ReviewReport`，避免调用方遗漏 scope 或需求来源。

**RequirementBundle** 是本次运行使用的不可变需求集合，包含每份需求的原文、条款定位、来源和内容哈希。RuleSet 可以内嵌该集合，也可以引用具有独立内容哈希的集合；运行时必须保存实际解析到的 bundle，不能只保存文件名。

**ReviewScope** 至少包含：

- `included_rules`：RuleSet 内实际选择的规则及版本。
- `subject_selectors`：需要纳入审查的快照、body、occurrence 等对象选择条件。
- `required_inputs`：本次范围必须提取的 Fact 查询；规则声明与范围声明取并集，不能只计算碰巧已有的数据。Fact 或已证明的 `ABSENT` FactGap 视为已解析；`UNSUPPORTED`、`UNKNOWN_UNIT`、`PARSE_FAILED` 或 `NOT_COMPUTED` 缺口保持未解析，产生 `SCOPE_INPUT_UNRESOLVED` 诊断并阻止完整性。
- `discovery_requirements`：需要完整发现的实体类型和装配范围。
- `scope_id`：上述规范化内容的哈希。

ReviewScope 定义“要查什么”，候选实体登记是本次运行的结果，不反向改写 scope。报告必须同时保存 scope 定义和实际候选清单。

### 6.2 Rule 结构

每条 Rule 至少包含：

| 字段 | 说明 |
|---|---|
| `rule_id` / `version` | 稳定标识和版本 |
| `requirement_refs[]` | 对应原始需求及条款 |
| `subject_selector` | 选择文件、body、occurrence 等适用对象 |
| `applicability` | 受限表达式，决定适用、不适用或无法确定 |
| `inputs[]` | 所需 Fact 查询和上下文键 |
| `checker` | 已注册检查器名称 |
| `parameters` | 阈值、容差和其他审核后的参数 |
| `severity` | 违规严重级别，不影响逻辑状态 |
| `review_type` | 可选的 `file_health / requirement_compliance / design_process_rule` 分类 |
| `source` | 规则解释的来源和审核信息 |

每个 input 声明 `required`、查询和可选默认值。可选输入只有在检查器声明了默认值语义时才能省略；否则缺失仍为 unknown。缺失处理由输入类型和检查器共同决定，详见 §6.4。

当前实现中，任一选中 Rule 带 `review_type` 时，报告为各类型输出四态计数摘要；该运行里的未分类 Finding 归入 `requirement_compliance`。完全旧的未分类运行仍输出 null 类型字段和 null 摘要；可选 null 不参与结构化哈希，因此旧报告及修改链的内容身份保持不变。`rule-packs/step-file-health/` 是有来源、适用范围和公开验证入口的 readiness-only 规则包，不代表通用设计或制造标准。其他工艺规则必须标明客户/标准/审核来源及目标语料验证，不能凭空声称通用 DFM 规则。

v0.1 只允许白名单比较、集合/计数、存在性和已注册领域检查器。RuleSet 不包含可执行 Python、shell 或动态 import。

### 6.3 首批检查器

P1 只设计少量通用检查器：

| 检查器 | 输入 | 用途 |
|---|---|---|
| `snapshot.status` | 快照状态和诊断 | 文件可读性、部分解析 |
| `fact.present` | Fact/FactGap | 必需声明或测量是否存在 |
| `numeric.compare` | 数值、单位、阈值、容差 | 外形、体积等明确约束 |
| `count.compare` | 整数计数和阈值 | 明确的对象数量要求 |
| `declared.value` | 已声明属性 | 材料、名称或零件号要求 |

通用壁厚和通用特征检查器只有在独立验证后才能加入，不属于 P1 基础检查器。

### 6.4 评估顺序与缺失语义

对每条规则和每个候选主体：

1. **评估适用性**：明确不适用才返回 `not_applicable`。
2. 适用性因缺少上下文无法确定时返回 `unknown`，原因记为 `APPLICABILITY_UNKNOWN`。
3. 收集输入；查询没有产生 Fact 或 FactGap 时，由 Reviewer 补建 `NOT_COMPUTED` FactGap。
4. 按输入和检查器处理缺口：
   - 普通数值、比较和声明值检查的任何必需输入缺失均为 `unknown`。
   - `fact.present` 仅在缺口为已证明的 `ABSENT` 时，对“必须存在”的要求返回 `violated`。
   - `PARSE_FAILED`、`UNSUPPORTED`、`NOT_COMPUTED`、未知单位或未知发现覆盖，即使对 presence 规则也只能返回 `unknown`。
   - 可选输入只有存在审核后的默认值才可继续，否则仍为 `unknown`。
5. 检查单位、数据范围和前置诊断。
6. 执行检查器，返回 `satisfied` 或 `violated`。

检查器和编排错误采用统一策略，不增加每规则自定义错误政策：

- RuleSet、参数或单位配置无效属于配置错误，不产生正常 ReviewReport。
- 可预期的数据不可用必须转成 FactGap，而不是异常。
- 未预期的检查器异常产生 `unknown / CHECKER_FAILED`，报告标记 `tool_error=true` 和 incomplete；可以输出部分 JSON 报告，但进程按内部错误处理，绝不能转成 satisfied。
- 无法继续的编排错误输出结构化错误对象；若无法生成符合 schema 的报告，不伪装为正常 ReviewReport。

缺少数据时不能默认 violated，因为“文件未声明材料”和“材料不符合要求”是两个不同结论。若 Requirement 明确要求必须声明材料，则由 `fact.present` 规则只在 ABSENT 已证明时判 violated。

### 6.5 总体状态

ReviewReport 的总体状态定义为：

- `non_compliant`：至少一个 violated。
- `incomplete`：没有 violated，但存在未知适用性、unknown、实体发现 partial/unknown、必需诊断未解决、检查器错误或范围为空。
- `compliant_for_scope`：所有适用审查项均 satisfied，且本次声明范围内规则覆盖、实体覆盖和发现均完整。

报告另有 `complete` 和 `tool_error` 字段。`non_compliant` 只表示已经发现违规，不表示其余审查已经完成；存在 violated 时仍可同时有 `complete=false`。`compliant_for_scope` 必须同时满足 `complete=true`、`tool_error=false`、`entity_discovery=complete`，且每个 decision_required 候选实体均为 fully inspected。

不使用无范围限定的“文件合格”。

### 6.6 候选登记与覆盖率

候选实体按固定算法产生：

1. 适配器为 ReviewScope 声明的实体类型和装配范围生成候选目录，并给出 `entity_discovery=complete / partial / unknown`。已知跳过或截断为 partial；无法判断是否遍历穷尽为 unknown；空目录本身不能证明 complete。
2. Reviewer 对目录中的每个实体执行 `subject_selectors`，按 EntityRef 去重并稳定排序，形成候选登记清单。选择器不得凭相似度补入未发现的实体。
3. 清单记录每个候选的规则评估、Fact/FactGap 和阻断诊断。候选登记属于 ReviewReport，不会修改不可变 ReviewScope。
4. 全部规则评估均为 not_applicable 的候选标记 `inspection_not_required=true`，不进入实体覆盖分母。其余候选都属于 `decision_required_entities`，包括适用性为 unknown 的候选；只有不存在任何 unknown、所有需要判断的评估均为 satisfied/violated、所有必需输入已解析且没有阻断诊断时，才标记 `fully_inspected=true`。violated 仍可以是完整检查。
5. 实体级规则没有任何候选时记录 `EMPTY_SCOPE`，不能将其当作 not_applicable 或 compliant_for_scope。

分母和比例固定如下：

- 审查项为“规则 × 候选对象”；`satisfied + violated + unknown` 构成需要判断的评估分母，`unknown` 不计为已覆盖，`not_applicable` 单独报告。
- `rule_coverage = (satisfied + violated) / evaluations_requiring_decision`，同时输出原始计数。
- 发现完整时，`entity_coverage = fully_inspected / decision_required_entities`，分母包含所有已登记且需要判断的候选，不能因适用性 unknown 而排除候选。
- 发现为 partial 或 unknown 时，真实总实体数和真实 `entity_coverage` 均为 unknown。可以另报 `discovered_only_inspection_ratio = fully_inspected / discovered_decision_required_entities`，但名称不得简写为 entity coverage，也不得显示为 100% 总覆盖。
- `entity_discovery=accepted` 不是合法状态；人工接受诊断不会把 partial/unknown 改为 complete。

报告同时输出发现状态、登记数、完整检查数、原始计数和有明确名称的比例，避免仅展示百分比。

---

## 7. 修改详细设计

当前仓库已实现本节契约的 STEP 纵向切片：`prepare_change` / `verify_change` 公共接口及对应 CLI、ChangeRequest/ChangePlan/SourceManifest 内容身份、可选 ApprovalRecord/ExecutionRecord 一致性检查和 ModificationReport。`cad_to_facts.records` 还提供从实际工作区字节构建 root/derived 清单、批准和执行记录的确定性接口；批准人、决定、时间和执行 attestation 必须显式提供，不能从文件存在推断。一次实际先批准、后执行、再验证的 text-to-cad 0.11.10 测试记录保存在维护者本地，不随公开仓库发布；公开的可重放示例见 `examples/change-loop/README.md`。早期历史 smoke 仍为 unattested。`prepare-change` 目前仅从 `numeric.compare` 的 violated/unknown Finding 派生目标。两个命令和记录构建器都不执行 CAD 或源脚本；完整状态机和外部批准工作流编排仍未实现。

### 7.1 ChangeRequest 契约

必需内容：

| 分组 | 内容 |
|---|---|
| 基线 | `base_artifact_sha256`、基线 `snapshot_id` / `snapshot_content_hash`、`base_factset_id`；source-backed 时的 `source_manifest_sha256` |
| 验证配置 | 固定的 `verification_profile`，包括修改前后读取与提取配置 |
| 来源 | `origin=review_derived / user_intended` 及相应的审查血缘或用户意图 |
| 目标 | EntityRef、装配路径或受限选择条件 |
| 前置条件 | 目标在修改前必须满足的 Fact 和数量约束 |
| 修改意图 | 期望约束，而非未经验证的底层几何操作 |
| 保持项 | 不得改变的尺寸、特征、装配、PMI 或声明属性 |
| 验收 | 修改后必须满足的检查及修改验收容差 |
| 比较策略 | 允许的预期变化、匹配方法和数值容差 |
| 输出 | `output_policy`：格式、工作区相对位置或逻辑目标；禁止覆盖基线 |

默认将输出格式、相对工作区位置和禁止覆盖作为请求语义，执行器的临时绝对路径只是展示/执行信息。若用户明确把某个绝对输出位置设为约束，则该规范化位置进入 ChangeRequest、ChangePlan 和 ApprovalRecord 的内容哈希；改变它同样使旧批准失效。当前验证器还会把实际 after SourceArtifact 位置与 `output_policy.path` 核对：绝对路径要求规范化后一致，相对路径要求与实际输出位置的末尾组件一致；不匹配为 `OUTPUT_LOCATION_MISMATCH`，即使其他几何检查通过也不能宣称满足输出策略。

仅为已归档证据的异地重放提供显式 `--replay-relocated-output`：当原策略是绝对路径时，只允许 `--after` 处存在相同文件名，输出位置检查必须说明原绝对目录未重新验证。该选项默认关闭，不接受不同文件名，不改写 ChangeRequest、ApprovalRecord 或 ExecutionRecord，也不得用于绕过实时修改中的位置失败。`examples/change-loop/` 保留真实记录并提供该重放的公共 CLI 回归。

`verification_profile` 至少固定适配器及版本、解析器/内核及版本、规范化解析选项、读取范围、提取器及版本、提取查询和相关 schema 版本。P2 默认只允许修改前后使用同一 profile；任一必要配置不同则标记 `PROFILE_INCOMPATIBLE`，不得用跨 profile 的数值或实体差异直接作出通过判定。可以进行独立的新文件审查，但它不替代兼容的前后比较。

对于 `review_derived` 请求，必须保存原 `review_run_id`、`finding_id`、RuleSet/RequirementBundle 内容哈希、ReviewScope ID 和 ReviewContext 内容哈希。复审沿用这些规则、上下文和 scope 选择条件，在新快照上重新登记候选并产生新的 ReviewRun；EntityRef 不直接跨快照复用。原 Finding 没有对应的新评估时，其解决状态为 unknown。

对于 `user_intended` 请求，保存明确的用户意图和本次提供的上下文，不伪造原 Finding，也不要求先存在原复审报告。没有原 ReviewRun 时，只执行请求中明确声明的验收和保持项检查。

请求内容变化会产生新的 ChangeRequest ID，并使旧批准失效。

### 7.2 ChangePlan 契约

ChangePlan 在 ChangeRequest 之外增加：

- 执行器及版本。
- SourceManifest 的完整性检查结果。
- 目标到执行器原生引用的映射。
- 具体源修改或建模操作。
- 每项验收和保持项的比较方法。
- 预期失效的引用和可能需要重建的 PMI/元数据。
- 执行器特定的受控载荷。

计划生成时必须验证目标唯一性。零个或多个匹配都停止计划，不能选择最近似对象。

### 7.3 批准与状态机

```text
draft
  → validated
  → awaiting_approval
  → approved
  → executing
  → verifying
  → passed | failed | incomplete
```

附加规则：

- draft/validated 可进入 rejected；执行前可取消。
- 基线哈希或 SourceManifest 变化时进入 superseded，必须重新计划。
- 批准绑定 ChangeRequest ID、ChangePlan ID、基线哈希和执行器版本。
- 请求、计划、执行器或基线任一变化都使批准失效。
- 只有 ApprovalRecord 对当前完整请求、计划、基线和执行器仍有效，才允许 approved → executing。
- 执行异常使工作流进入 failed；必要比较无法执行进入 incomplete。
- 不允许从 draft 或 awaiting_approval 直接进入 executing。

这里的状态机描述工作流编排，不与 ModificationReport 的验证状态混用。执行失败且没有可验证输出时，工作流为 failed，报告的 `verification_status` 通常为 incomplete；若基线身份、前置条件或提供的记录绑定检查已证明失败，则报告为 failed。`verification_status=passed` 仍要求所有必需检查通过，而不只是“文件能打开”。

**ApprovalRecord** 至少包含：`approval_id`、ChangeRequest ID、ChangePlan ID、基线导出物哈希、source-backed 基线清单哈希、执行器及版本、受控载荷哈希、批准者标识、决定和时间。执行前必须重新计算并核对请求/计划内容哈希、计划到请求的引用、当前基线和执行器/载荷；只比较调用方传来的一段 ID 不足以验证批准。批准仅覆盖该完整计划一次，不覆盖未来输出或其他计划。

**ExecutionRecord** 至少包含：`execution_id`、ApprovalRecord ID、实际 ChangeRequest/ChangePlan ID、实际执行器及版本、实际输入源和基线哈希、受控载荷哈希、新源/新导出物哈希、新 SourceManifest 哈希、执行结果、日志证据引用和时间。记录构建器还要求并保存 `attested_by` 与 `attestation`，明确谁在声明什么。当前实现的 `mode=attested_local` 表示本地执行声明，`mode=observed_external` 表示外部观察记录；两种模式都只在报告保留声明/观察来源，不自动升级为独立密码学证明。

验证时逐字段比对批准、计划、执行记录和实际注册的新文件。没有 ExecutionRecord 时 `execution_provenance=unattested`；记录完整且一致时为 `attested`；任何关键字段矛盾时为 `contradicted`。attested 只表示存在一致的可追溯执行声明，不把外部声明升级为独立密码学证明。验证器不得仅凭“出现了一个新 STEP”自行补建 ExecutionRecord。

P2 默认采用外部 skill handoff：由 agent 调用单独安装的 text-to-cad CAD skill（其命令接口为 `cad run` 构建源脚本、`cad model export` 导出新文件），再对本项目提供的新文件进行 verify。text-to-cad/cad-server 不进入本项目 Python 依赖，也不要求在本项目内嵌其运行时。外部 handoff 必须允许缺少执行声明，并明确输出 unattested；skill 被调用或出现了一个新 STEP 都不能单独证明批准计划已执行。

### 7.4 目标绑定

优先级如下：

1. 执行器原生且当前源版本内有效的引用。
2. SourceManifest 中可追踪的源对象与导出物映射。
3. 源生标识和装配路径。
4. 带容差的几何签名，仅作为辅助证据。

无论采用哪种路径，执行前都必须重新计算前置 Fact。前置条件不满足时停止。

### 7.5 验证输入与修改后比较

`verify(VerificationRequest)` 的完整输入包括：

- 原 ChangeRequest 和 ChangePlan，而不只是两个文件路径。
- ApprovalRecord；没有时只能做未证明已获批准的输出验证。
- ExecutionRecord；没有时执行来源为 unattested。
- 修改前后原始 SourceArtifact，以及 source-backed 工作流的前后 SourceManifest。
- 请求引用的基线 ModelSnapshot/FactSet，或可按固定 profile 重放并核对其内容哈希的输入。
- `review_derived` 请求的原 ReviewReport 及其可解析的 RuleSet、RequirementBundle、ReviewScope、ReviewContext 和 Reviewer 版本。
- 按相同 verification profile 产生的新 ModelSnapshot 和 FactSet。

source-backed 验证还必须执行 `manifest_validation`：

1. 重算两份清单哈希，旧清单必须等于请求绑定值并包含 base artifact，新清单必须包含实际 after artifact。
2. 新清单必须为 `lineage_kind=derived`，且 `parent_manifest_sha256` 精确等于旧清单哈希。
3. 每个 `modified_from[]` 条目的新源必须属于新清单、旧源必须属于旧清单；源集合中的修改、新增和删除必须与批准的 ChangePlan 一致，不能留下未声明的源差异。
4. ExecutionRecord 中的实际输入源、新源和新清单哈希必须与上述对象一致。

缺少新清单时 `manifest_validation=not_provided`、来源为 unattested；提供的清单或执行记录存在上述矛盾时 `manifest_validation=failed`、来源为 contradicted。该结果独立于输出几何/规则验证状态。

验证器重新核对原始字节哈希、基线快照/FactSet 身份和清单包含关系。基线 artifact 不匹配属于 stale-base 配置错误；重放后基线快照内容不匹配则必需比较为 unknown，不能选择性采用较有利的结果。profile 不兼容、实体发现 partial/unknown 或新文件必需 FactGap 都使相应比较为 unknown。

验证分四组：

| 分组 | 内容 |
|---|---|
| 目标验收 | 修改目标是否达到期望约束 |
| 保持项 | 明确要求不变的事实是否仍在容差内 |
| 非目标变化 | 是否出现未声明的新增、丢失或拓扑变化 |
| 数据保留 | PMI、材料、名称、装配和外部声明是否保留或明确失效 |

数据保留必须显式声明逐项检查或 `data_retention_not_applicable=true`；两者都缺失时记录 `DATA_RETENTION_UNDECIDED`，验证不得 passed。`explicitly_invalidated` 只有匹配后的 after 数据出现已证明的 `ABSENT` 缺口才通过；`UNSUPPORTED`、`UNKNOWN_UNIT`、`PARSE_FAILED` 或无法匹配保持 incomplete。

匹配规则：

- 文档级指标直接比较。
- 优先使用源生标识、源操作映射和装配路径。
- 几何签名不能单独证明身份。
- 必需对象无法匹配时，相应结果为 unknown，报告不能 passed；只有有充分证据证明一个应保持的非目标对象确实消失时才是 failed。
- 必需发现不完整时，不能把“已发现对象均未变化”当作完整的非目标检查。
- 已证明的意外新增、丢失、变化或数据丢失为 failed；无法建立匹配、无法确定是否变化为 unknown。

数值容差按检查类型隔离：

- 目标验收、保持项和前后差异比较使用 ChangePlan 中逐项固定的容差；该容差来自 ChangeRequest 的验收/比较策略，并在批准前解析到每项检查。
- 原规则复审继续使用原 RuleSet 的阈值和容差，不能改用较宽松或较严格的修改验收容差来制造期望结论。
- 没有适用容差，或容差低于已声明的数值方法可靠性限制时，相关浮点比较不得用于通过判定。

#### 7.5.1 实体匹配（当前实现）

仓库的内部库模块 `cad_to_facts.matching` 固定上述匹配契约，并已被 `verify_change` 正式用于修改前后比较；它没有独立 CLI，也不执行或批准修改。匹配结果本身不等于完整修改验证：

- `EntityMatchingProfile` 显式选择 `native_ref`、`adapter_key` 或 `fingerprint` 方法。`native_ref` 指定引用类型；`fingerprint` 指定谓词列表和一个绝对/相对容差。方法专属字段混用属于配置错误。
- `EntityMatchRequest` 绑定前后 `ModelSnapshot`、profile、显式 `required_baseline_entity_ids`，以及 fingerprint 方法所需的两个 `FactSet`。请求、profile、快照和 FactSet 的内容 ID 都会重算校验。
- `match_entities(request) -> EntityMatchReport` 返回逐实体 `matched / unmatched / ambiguous / unresolved`，以及 `unmatched_candidate_entity_ids` 和诊断。只有所有必需实体均为 `matched`、前后快照均为 `ready`、发现均为 `complete` 且解析 profile 一致时，报告才是 `complete`；其余一律 `incomplete`。未匹配的候选实体单独列出，本身不使匹配不完整；它们是否属于预期变化由上层验证判断。
- `adapter_key` 只是显式声明的遍历键回退，不证明跨修订身份；`native_ref` 的稳定性仍取决于导出器；`fingerprint` 的匹配只说明在声明谓词和容差内数值一致，不能单独证明对象身份。
- 重复基线键、重复候选键、多个基线实体争用同一候选、单位不一致、缺少必需 Fact 或候选 Fact 都产生 `ambiguous` 或 `unresolved`，不能猜测最近似对象。解析 profile 不一致时所有必需结果均为 `unresolved`。


### 7.6 ModificationReport

至少包含：

- 原 SourceArtifact；新 SourceArtifact 按条件引用。
- source-backed 工作流的原 SourceManifest、新 SourceManifest 和 `manifest_validation`；非 source-backed 工作流明确为 not_applicable。
- ChangeRequest、ChangePlan，以及按条件提供的 ApprovalRecord、ExecutionRecord 和一致性检查。
- 基线 snapshot_id、snapshot_content_hash、factset_id；新快照/FactSet 按条件引用，并记录 verification profile 兼容性。
- 验收、保持项、非目标变化和数据保留的逐项 `passed / failed / unknown`、必需标志与证据。
- review_derived 修改的原 ReviewReport、原 Finding 解决状态和按条件产生的新 ReviewReport；user_intended 的原审查引用为 not_applicable。
- 独立的 `verification_status=passed / failed / incomplete` 与 `execution_provenance=attested / unattested / contradicted`。
- `change_observed=changed / no_change / unknown`、未解决问题和需要人工复核的项目。

所有条件引用统一使用 `{state, ref?, reason_code?}`，当前实现的状态为 `present / missing / not_provided / not_applicable`，不使用 null 占位：

- 执行失败而没有输出，或 CLI 的 after 文件不存在时，新 artifact/snapshot/FactSet 为 missing，`change_observed=unknown`，输出验证通常为 incomplete；若基线身份、前置条件或提供的记录绑定检查已证明失败，则为 failed。
- 调用方未提供批准、执行记录或 source-backed 新清单时为 not_provided，执行来源为 unattested。
- user_intended 没有原 ReviewRun 时，原审查引用为 not_applicable；review_derived 缺少必需原审查输入时为 not_provided，原 Finding 解决状态为 unknown。
- 只有 `state=present` 才能带有效 ref；其他状态必须给出原因。这样执行失败、纯用户意图和缺少新清单的路径都能生成符合契约的终端报告。

`verification_status` 聚合所有必需检查，包括输出、清单和记录绑定检查；`execution_provenance` 单独报告执行来源，不能替代或掩盖检查结果：

| 条件 | verification_status |
|---|---|
| 任一必需检查已证明 failed、要求解决的原 Finding 复审仍 violated，或完整原 RuleSet/Scope/Context 的 after ReviewReport 为 non_compliant | `failed`，优先于所有 incomplete 条件 |
| 没有已知失败，但任一必需检查/原 Finding 为 unknown，after ReviewReport 不是完整的 compliant_for_scope，或存在无法匹配、发现不完整、必需 FactGap、profile 不兼容 | `incomplete` |
| 所有必需检查均 passed，要求解决的原 Finding 已 satisfied，完整原规则复审为 compliant_for_scope，且比较范围完整、profile 兼容 | `passed` |

`passed` 不表示批准计划已被执行；该结论必须另看 `execution_provenance`。缺少批准/执行记录或新 SourceManifest 时可以完成输出验证，但来源保持 unattested，报告不得自称“已验证的 source-backed 批准执行”。记录与文件或计划矛盾时来源为 contradicted；相应记录绑定检查同时为 failed，因此 `verification_status` 不得为 passed，也不能掩盖输出检查本身的 failed 或 incomplete。仅有无效 ApprovalRecord 而没有 ExecutionRecord 时，approval_validation=failed，执行来源仍为 unattested。

原文件与新文件哈希相同只确定 `change_observed=no_change`，不自动通过或失败，也不增加状态机节点：仍需执行全部验收和保持项检查，目标已满足时可以 passed，目标仍 violated 时 failed，无法判断时 incomplete。哈希不同也只确定 changed，不代表修改正确。重试验证创建新 ModificationReport，不修改既有终端报告。

---

## 8. 下游数据详细边界

### 8.1 BOMExtract

核心结构：

| 字段 | 说明 |
|---|---|
| `line_items[]` | 按 PartDefinition 形成的行项目 |
| `occurrence_refs[]` | 每行包含的实例证据 |
| `quantity` / `quantity_state` | 实例数量及其 `known / observed / unknown` 语义 |
| `counted_occurrence_refs[]` | 实际计入数量的活动实例证据 |
| `declared_properties` | 零件号、名称、材料等声明值 |
| `assembly_links[]` | 父子装配关系 |
| `missing_inputs[]` | ERP 或其他系统仍需补充的字段 |
| `coverage` / `diagnostics` | 实例发现和属性提取完整性 |
| `provenance` | 源文件、快照和提取器版本 |

默认数量只统计已确认的活动 Occurrence。完整结构下可标记 `known`；partial/unknown 或源 PRODUCT/NAUO 与 XCAF 对账不一致时只能标记 `observed`，数值仅表示已观察数量；任一相关实例状态未知时 `quantity=null`、`quantity_state=unknown`。抑制状态、外部引用或实例关系未知时，相关行或整份 BOMExtract 必须标记不完整。`coverage` 分别统计 `known / observed / unknown` 行项目数，三者之和必须等于 `definition_total`，使每个叶子行项目的数量状态都有明确归属。

行项目不能使用名称作为唯一合并键；优先使用源生 PartDefinition 标识。

### 8.2 ProcessCardInput

允许包含：

- 零件身份和版本。
- 已声明材料和表面处理。
- 几何测量。
- 经明确标记的特征候选。
- PMI 和检验特性。
- 每个特性的证据和关联状态。
- 需要外部补充的材料确认、毛坯、设备、批量等输入清单。

当前 `facts process-input` 只实现上述契约的受限单 solid 纵向切片：只接受 STEP `single_part` 快照，要求恰好发现一个 solid，并投影已有 `volume`、`area` 和三个 `bbox.extent.*` Fact。默认必需用户上下文为 `material / stock / batch_size`，可用显式 `--require-context` 替换；上下文值只标为 `user_supplied`，不能变成 declared material Fact。`declared_material`、`semantic_pmi` 和 `validated_features` 当前均产生 `UNSUPPORTED` missing input，默认是可选缺口；通过 `--require-design-input` 声明为必需时阻止完整性。语义 PMI 已可由独立的 `facts pmi` 提取，但本命令不将其投影为 ProcessCardInput 字段，因此仍保留 `semantic_pmi` 投影缺口；没有特征或材料推断。

输出绑定 artifact、snapshot/content hash、FactSet、ReviewContext、准备器版本和显式选项，并包含 `external_inputs`、`missing_inputs`、coverage 与 diagnostics。`complete=true` 只表示该受限几何/上下文契约完整：快照 ready/complete、恰好一个 solid、五项几何 Fact 齐全、必需缺口为零且无未解决的阻断诊断。零/多 solid 添加 `PROCESS_SINGLE_PART_REQUIRED`，不隐式选取任何一个。上下文中嵌套的工序、装夹、设备/刀具、切削参数、工时或工艺路线决策键属于配置错误，不能通过改名绕过边界。

明确不包含：

- 工序顺序和工艺路线。
- 装夹方案。
- 设备、刀具和夹具选择。
- 切削参数和工时。
- 工艺卡模板渲染。
- ERP/CAPP 字段映射、同步和审批。

### 8.3 PmiExtract（当前实现）

语义 PMI 是与几何关联、机器可解释的声明信息，不属于 `FactSet`，也不由特征识别产生。`facts pmi` 重新以 XCAF GD&T 模式读取同一 STEP artifact，输出：

| 字段 | 说明 |
|---|---|
| `annotations[]` | 声明的尺寸、几何公差和基准；含值、单位、公差、修饰符、基准引用、来源和几何关联 |
| `inventory` | 原始 STEP 中的尺寸、表示、几何公差、基准、基准要素、基准体系、图形标注和不支持类别计数 |
| `coverage` | 按类别的观察/提取/有值计数和链接状态；`discovery` 为 `complete / partial / unknown` |
| `gaps[]` | 值、单位、公差、基准标识、链接或不支持类别的明确缺口 |
| `diagnostics[]` | 读取器符号缺失、单位上下文歧义、覆盖不完整和读取失败等诊断 |
| `units` / `unit_contexts` | 从 PMI 表示上下文解析出的规范单位及观察到的上下文计数 |
| `status` / `complete` | `ready / partial / failed` 与“本 profile 是否完整覆盖所观察内容” |

提取边界：

- XCAF 提供尺寸和几何公差的值与形状引用；原始 STEP 模型提供实体清单和表示/公差单位。二者都不是完整 AP242 实现。
- 只输出声明存在且读取器能给出的值。声明对象存在但没有可用标称值、单位无法唯一确定或链接无法映射时，注解仍可存在，但 `value=null` 或 `link_status != resolved`，并由 `PmiGap` 说明原因；不创建零值或推测值。
- 公差分为绝对 `limits` 和 `deviation_magnitudes`。OCCT 只暴露偏差幅值时，`sign_convention=not_reported_by_reader` 并产生诊断，不推断正负方向。
- 尺寸单位要求文件内全部尺寸表示收敛到单一长度单位和单一角度单位；几何公差单位要求全部公差幅值收敛到单一长度单位。当前 XCAF 对象没有逐尺寸表示指针，因此混合单位保守地不输出值并产生 `PMI_UNIT_AMBIGUOUS`，而不是按邻近标注或系统单位猜测。XCAF 返回的标称值、长度类公差和角度 limits 使用读取器系统单位（mm、deg）；提取器按表示上下文换算回声明单位，避免把 `0.5 in` 报成 `12.7 in`。角度 deviation 幅值保持声明角度单位。
- 自写 OCCT AP242 夹具覆盖 mm/cm/in/rad 换算、deviation/limits 尺寸、角度尺寸、基准引用、材料修饰符和基准体系缺口；这些夹具只用于回归，不构成外部 exporter 互操作性或完整 AP242 一致性证据。
- 链接先由 XCAF 引用形状映射到 PMI 文档中的 owner solid，再仅在体积、面积、质心和包围盒指纹唯一匹配时映射到快照 `solid:N`。`resolved / unresolved / absent` 只描述本次投影；重复几何、未知单位或无法唯一匹配时保持 unresolved/absent，不选择最近对象。面/边/顶点不获得稳定面 ID。
- 图形标注（`DimensionPresentation` / `CommonLabel`）计入 `inventory.presentation_entities`，不产生注解或缺口。基准要素作为基准关联的支撑实体通过 datum 链接体现，不单独输出；基准体系、基准目标和表面纹理/光洁度计入不支持类别，产生 `PMI_UNSUPPORTED_TYPE` 并使 `discovery=partial`，不能被静默视为已完整提取。
- 文件没有语义 PMI 时返回 `status=ready`、`complete=true` 和空注解/缺口；这是“未声明 PMI”的明确结果，不是读取失败。读取/传输失败返回 `status=failed`、`PMI_READ_FAILED` 和 `complete=false`。
- `complete=true` 只表示该 profile 对其可观察类别完成了对账，不表示 AP242 一致性、尺寸/公差正确性、检验可行性或制造合格。PMI 目前不投影到 `process-input`、审查规则或 BOM；`process-input` 的 `semantic_pmi` 仍是 `UNSUPPORTED` 设计输入缺口。

### 8.4 外部输入

调用方可通过显式本地上下文补充少量参数。所有外部值都记录来源为 `user_supplied` 或 `external_reference`，不能伪装成从设计文件读取的 declared Fact。

---

## 9. CLI 与输出行为

`inspect`、`query`、`resolve`、`features`、`orient`、`ask`、drawing/STEP `render`、`review`、`prepare-change`、`verify-change`、`bom`、受限 `pmi` 和受限单 solid `process-input` 已有实现，当前配置输入为 JSON。`inspect`、`review`、`prepare-change` 和 `pmi` 接受显式 `read_scope`；`resolve`、`features`、`orient`、`bom` 和 STEP `render` 固定使用 assembly profile，`ask` 对 STEP 使用 assembly profile、对 DWG/DXF 使用 drawing profile，`process-input` 固定使用 single_part profile。`pmi` 额外重新读取 XCAF GD&T，默认使用 single_part 绑定链接。`doctor --check` 只检查运行环境，不解析 CAD；其可选 ODA 文件路径必须显式提供，且只读哈希、不启动转换器。其他格式仍按各自 profile 的已实现范围为限。

### 9.1 命令职责

| 命令 | 产生 | 不产生 |
|---|---|---|
| `facts inspect` | SourceArtifact、ModelSnapshot 摘要、选择性 FactSet | 完整模型 dump |
| `facts resolve` | TargetResolution、候选及世界坐标/空间证据 | 自动消歧、持久身份、源码位置 |
| `facts features` | FeatureRecognitionReport、名称候选和有界通孔几何 | 通用门窗/孔识别、完整特征数量 |
| `facts orient` | 六向 OrientationReport、可选假设 ViewSpecification | 源声明或功能正面证明 |
| `facts ask` | STEP QuestionSpec 或图纸 DrawingQuestionSpec 对应的 AnswerReport、证据与缺口 | 通用 NLP、通用图纸语义、推断 Fact、无缺口语义理解 |
| `facts render` | 新 SVG；STEP 另有 ViewRenderManifest | Fact、视觉/几何等价证明、像素尺寸 |
| `facts review` | ReviewReport | 自动修改 |
| `facts prepare-change` | ChangeRequest / ChangePlan | 隐式执行 |
| `facts verify-change` | ModificationReport | 对源文件的修改 |
| `facts bom` | BOMExtract | ERP 写入 |
| `facts pmi` | PmiExtract | Fact、检验计划、AP242 合格证 |
| `facts process-input` | ProcessCardInput | 工艺规划或最终工艺卡 |

P1 的 review 调用显式提供全部逻辑输入：

```bash
facts review part.step --requirements examples/requirements.json \
  --rules examples/rules.json --scope examples/review-scope.json --context examples/review-context.json
```

RequirementBundle 不会自动变成可执行 RuleSet，也不存在隐含的“全部规则、全部实体”默认 scope。将来即使提供快捷方式，也必须先物化完整 RuleSet 和 ReviewScope 并纳入 ReviewRun 身份。

`prepare-change` 的实际命令需要完整原审查输入和显式准备规格；source operations 需要已验证的基线清单：

```bash
facts prepare-change --report review.json --finding finding-1 --before old.step \
  --requirements requirements.json --rules rules.json --scope scope.json --context context.json \
  --spec prepare-spec.json --before-manifest old-manifest.json
```

它输出绑定的 ChangePreparation（ChangeRequest + ChangePlan），不执行 CAD。当前只从 `numeric.compare` 的 violated/unknown Finding 派生目标。

`verify-change` 的逻辑输入契约如下；它验证既有交接和新文件，不负责执行：

```bash
facts verify-change --request change.json --plan plan.json \
  --approval approval.json --execution execution.json \
  --before-manifest old-manifest.json --after-manifest new-manifest.json \
  --origin-review review.json --before old.step --after new.step
```

`--origin-review` 仅用于 review_derived 请求，且引用的原始不可变规则、scope 和上下文必须可解析。source-backed 验证要求前后清单；省略 approval/execution 不阻止独立输出验证，但结果必须标记 unattested。CLI 还必须能加载请求固定的基线快照/FactSet，或按 profile 重放并核对它们，不能只接收 before/after 两个路径就声称验证了批准计划。

BOM 的实际命令为 `facts bom assembly.step [--require-property name]`。输出包含可解析的 definitions、occurrences、assembly_links、line_items、missing_inputs、coverage 和 diagnostics；不输出 ERP 写入或工艺规划。除 name 外的必需属性当前为 UNSUPPORTED。

### 9.2 输出流

- stdout 只输出符合 schema 的 JSON。
- 人类日志和调试信息进入 stderr。
- 结果中的诊断与进程日志分离。
- 输出文件使用新路径和独占创建，不覆盖输入文件或既有输出；STEP 视图成对输出失败时只清理本次新建成员。

### 9.3 进程结果

- 成功生成结构化报告即表示命令完成；Review 中存在 violated 不等同于 CLI 运行错误。
- 调用/配置错误、无法生成报告和内部执行错误使用不同退出类别。当前实现：报告或检查结果成功产生时为 0（包括 `non_compliant` 与 `incomplete`）；配置/输入错误为 2，并在 stdout 输出 `{"error": {"category": "configuration_or_input", ...}}`；内部错误或报告带 `tool_error=true` 时为 3。
- 参数解析错误也输出同一 JSON 错误对象，不向 stdout 混入非 JSON 文本。
- CI 是否需要因 violated 返回非零，由显式 `--fail-on` 选项控制，不能默认混淆“审查发现违规”和“工具自身失败”。

### 9.4 大模型与大型文件

- inspect 默认摘要。
- 实体查询必须支持限制数量和分页游标。
- 达到上限时返回 `truncated=true` 和下一游标，不能将截断结果描述为完整集合。当前 `inspect --limit` 默认为 20，输出 `selection.entity_total / entities_returned / truncated / next_cursor`。
- P1 不引入缓存；后续缓存只能以 snapshot_id 为键，缓存不是事实真源。

---

## 10. 错误、确定性与安全

### 10.1 错误语义

- 可预期的数据缺口使用 FactGap。
- 可继续的部分解析使用 partial ModelSnapshot 和 Diagnostic。
- 无法继续的解析使用 failed ModelSnapshot，仍可进行文件健康审查。
- 模块实现错误不能静默转成 ABSENT。
- 所有公开输出在离开核心模块前进行结构验证和语义不变量检查。

### 10.2 确定性条件

相同语义结果的前提是：

- 相同 SourceArtifact。
- 相同适配器、解析器/内核和规则实现版本。
- 相同规范化参数、RuleSet 和 ReviewContext。
- 相同声明的数值容差。

不承诺不同内核、平台或线程调度下的浮点位级一致。集合输出采用稳定排序；时间戳和纯展示用绝对路径不参与内容比较，语义输出位置及其他影响行为的路径仍按 §4 纳入内容身份。

### 10.3 安全

- 所有 CAD 文件、压缩包和源脚本都视为不可信输入。
- 规则配置不允许任意代码执行。
- 源脚本必须经过批准，并在隔离、资源受限的环境运行。
- 解析和外部转换设置文件大小、时间、内存和输出限制；具体默认值通过 P0 基准确定。
- 外部转换器路径必须显式配置，临时目录独立，源文件只读。
- 默认不上传源文件、快照、截图或结构化结果。

---

## 11. 验证设计

### 11.1 测试层

| 层 | 验证内容 |
|---|---|
| 契约测试 | JSON Schema、必填字段、单位维度、引用完整性 |
| 语义不变量 | Fact 不带空值、unknown 不算覆盖、无匹配不得通过 |
| 适配器一致性 | 同一 fixture 在不同运行中得到相同语义快照 |
| 规则测试 | satisfied / violated / unknown / not_applicable 及分母 |
| 工作流测试 | 审查→修改→验证、BOM、工艺输入端到端 |
| 恶意/损坏输入 | 崩溃、超限、截断、部分解析和临时文件清理 |
| 对照测试 | 与 cad-mcp-server、cadtokens 或独立解析结果比较 |

### 11.2 P1 必过用例

1. 解析解零件的体积、面积和包围盒在声明容差内。
2. 英寸文件不会被默认解释为毫米。
3. 无单位输入产生 FactGap，不产生假设单位 Fact。
4. 解析失败仍产生文件健康 ReviewReport。
5. 已证明 ABSENT 的材料声明使“必须声明材料”violated，而“材料必须为 X”因缺少比较值为 unknown；PARSE_FAILED 对两者都不能当作 ABSENT。
6. unknown 不增加审查覆盖率。
7. not_applicable 不拉低覆盖率，但必须列出原因。
8. 实体发现 partial/unknown 时真实 entity coverage 为 unknown；discovered-only 比例必须明确命名，不能输出 100% 总覆盖或 compliant_for_scope。
9. 相同版本化输入重复运行得到相同语义报告。
10. stdout 始终为合法 JSON，日志不混入其中。
11. 必需查询既无 Fact 也无 FactGap 时补建 NOT_COMPUTED，并返回 unknown。
12. 检查器异常映射为 unknown / CHECKER_FAILED 和 tool_error，绝不转成 satisfied；无效 RuleSet 不产生正常报告。
13. 实体级规则候选为空时记录 EMPTY_SCOPE，不得判 compliant_for_scope。
14. 影响读取范围的 accepted 诊断仍为 unresolved，不能使快照 ready；只有带证据的 resolved 才解除阻断。
15. 完整发现下，适用性 unknown 的候选仍进入实体覆盖分母，不能得到 100% entity coverage。

### 11.3 P2 必过用例

1. 修改前后 SourceManifest 分别绑定各自源与导出物；缺少新清单时不得声称建立了完整 source-backed 来源链。
2. 修改请求、计划、受控载荷、执行器、基线或语义输出位置变化后旧批准失效；纯展示路径变化不伪造新请求。
3. 旧基线哈希被拒绝；基线快照重放不一致时必需比较为 unknown。
4. 目标不唯一时停止，不选择近似对象。
5. 原文件和原可编辑源保持不变，新源与新文件使用新路径。
6. 目标约束通过但保持项失败时总体失败；同时存在未知项时已知失败仍优先。
7. 必需实体无法匹配、发现不完整或 profile 不兼容时总体 incomplete，不得 passed。
8. 已证明非目标实体意外丢失时报告 failed；仅无法确认是否丢失时为 unknown/incomplete。
9. PMI 或材料丢失时明确报告，不能仅因几何验收通过而通过。
10. no-op 输出标记 change_observed=no_change，并独立按验收条件判断 passed/failed/incomplete。
11. 输出检查全部通过但没有 ApprovalRecord/ExecutionRecord 时，verification_status 可 passed，execution_provenance 必须为 unattested；记录矛盾时为 contradicted。
12. review_derived 修改固定原审查输入；原 Finding 没有新评估时为 unknown，复审仍 violated 时修改验证 failed。
13. 修改验收使用 ChangePlan 容差，原规则复审使用 RuleSet 容差；替换任一容差都会改变运行身份且不得混用。
14. user_intended 修改无需伪造原 ReviewRun，但仍执行请求声明的全部必需验收和保持项。
15. root 清单省略父引用；derived 清单的 parent 必须等于旧清单哈希，modified_from 和全部源差异必须与批准计划一致，否则 manifest_validation=failed、来源为 contradicted。
16. 无输出执行失败、user_intended 和缺少新清单均能生成终端报告，当前条件引用分别使用 missing/not_applicable/not_provided，不用 null 冒充已引用对象。

### 11.4 P3/P4 必过用例

- 一个 PartDefinition 的多个活动 Occurrence 得到正确数量。
- 同名但不同定义的零件不能合并。
- 抑制/外部实例状态未知时 BOMExtract 标记不完整。
- ProcessCardInput 不含工序、装夹、设备/刀具选择或加工参数字段。
- 外部输入与设计文件声明在 provenance 中可区分。

---

## 12. 编程前的设计交付清单

### P0 必须完成

- [x] 用真实 text-to-cad 项目制作一份 SourceManifest 样例。
- [ ] 确认 text-to-cad 源对象、原生引用和导出物之间可建立的映射。
- [x] 确认 OCP STEP 单位、装配和源生实体引用的最小读取路径（实体 ID 仍不承诺跨修订稳定）。
- [ ] 评估 cadtokens 与 OCP 的 PMI/几何关联键，不能假设两边 F7 一致。
- [ ] 建立首批解析解、NIST 和真实文件的下载清单、哈希及预期结果。
- [ ] 与 cad-mcp-server/cadtokens 确定至少一组对照任务。
- [ ] 完成本文所有公共 JSON 示例的实际 schema 评审。

### P1 编程前冻结

- [x] SourceArtifact、ModelSnapshot、EntityRef、FactSet、FactGap。
- [x] Diagnostic 机器码初始列表。
- [x] Rule/RuleSet、RequirementBundle、ReviewScope、ReviewContext 和五个基础检查器。
- [x] ReviewReport 四态、总体状态、候选登记和覆盖率。
- [x] inspect/review 的 stdout、退出行为和输出限制。
- [x] P1 验收用例的输入和预期结果。

### P2 编程前冻结

- [x] 前后 SourceManifest 的真实构建验证方式。
- [x] ChangeRequest/ChangePlan 的目标选择、固定 profile 和原审查血缘。
- [x] ApprovalRecord/ExecutionRecord 的字段、验证和外部 handoff 信任语义。
- [x] text-to-cad handoff 的具体交接样例。
- [x] 修改前后比较矩阵、容差隔离和无法匹配的处理。
- [x] ModificationReport 的状态矩阵、no-op、执行来源与复审报告的关联。
- [x] P2 验收用例的输入和预期结果。

这里的勾选表示设计契约已有可执行实现与回归用例，不表示所有工业语料、外部执行证明或完整工程状态矩阵均已完成。

### 需要通过技术验证而非文档猜测的问题

1. text-to-cad 的原生引用能否在修改后可靠映射到导出 STEP。
2. cadtokens 与 OCP 的 PMI 探测结果能否通过 STEP 源生实体稳定关联；当前 `facts pmi` 只在 PMI-document solid 与快照 solid 的指纹唯一匹配时给出链接，不声称源生实体级稳定身份。
3. 哪些解析选项会影响 snapshot_id 和实体遍历顺序。
4. 大文件的资源限制和分页默认值应如何设定。
5. 哪些“非目标拓扑变化”可以可靠自动识别，哪些必须保持人工复核。

---

## 13. 设计完成判据

只有满足以下条件才进入对应阶段编程：

- 公共术语无歧义，Fact、Finding、Inference 和 WorkProduct 不混用。
- 所有输入、输出、状态和错误路径都有明确契约。
- 源模型与导出物的版本关系有真实样例。
- 每个“通过”结论都有可执行的验收条件。
- 每个无法确定的路径都有 unknown、FactGap 或 incomplete，而不是默认成功。
- 下游和外部系统边界没有隐式连接器或企业数据依赖。
- 验收语料、预期结果和对照方法先于实现确定。
