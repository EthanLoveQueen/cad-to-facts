# cad-to-facts —— 设计文件审查与工程工作流 skill · 方案

> 版本：修订版，2026-11-13  
> 核心变化：项目不再以“统一所有格式的 IR”为产品目标，而以**可信事实、文件审查、可验证修改和下游数据准备**为主线。  
> 详细设计：`docs/detailed-design.md`；领域术语：`GLOSSARY.md`。

## 0. 项目定位

### 要解决的问题

工程设计文件正在被越来越多地交给 agent 处理，但仅有自然语言能力并不足以完成工业任务：

- 审查设计文件时，需要准确的几何、装配、PMI 和属性数据，不能靠截图猜数值。
- 修改设计文件时，需要知道改的是哪个版本、哪个对象，以及修改后是否满足约束。
- 生成 BOM、准备工艺卡数据时，需要区分文件中已有的事实、推导结果和仍需外部补充的信息。

现有开源项目已经分别提供了几何内核、格式解析器、PMI 读取、CAD 控制和生成式建模能力。本项目不再假设“理解侧完全空白”，也不重复实现这些基础能力。

### 一句话定位

**cad-to-facts 为 agent 提供可追溯的设计文件事实，并在此基础上完成需求审查、可验证修改交接和下游任务的数据准备。**

它由四类能力组成：

1. **事实提取**：从设计文件获得带证据、单位、方法和诊断的数据。
2. **文件审查**：根据明确需求、设计标准和上下文输出合规结论及覆盖率。
3. **修改交接**：把修改意图转成结构化 `ChangeRequest`，交给 text-to-cad 等执行器，并验证修改结果。
4. **下游数据准备**：输出模型 BOM、工艺卡输入数据等中立结构化结果，由外部系统继续处理。

### 与 text-to-cad 的关系

text-to-cad 负责建模和修改执行；cad-to-facts 负责：

```text
读取现状 → 找到有证据的问题 → 明确修改目标与验收条件
→ 交给 text-to-cad → 重新读取结果 → 验证修改并复审
```

两者的主要衔接产物不是一段自然语言提示词，而是带版本、目标、约束和验收条件的 `ChangeRequest`。text-to-cad 以单独安装的 CAD skill 形式由 agent 调用；本项目不内嵌其运行时，也不把 text-to-cad/cad-server 加入 Python 依赖。skill 调用只负责执行交接，执行来源仍须由 `ExecutionRecord` 单独声明，否则保持 `unattested`。

### 首个有辨识度的演示

首个完整演示不是“支持多少种格式”，而是完成一次闭环：

```text
读取零件与需求
→ 审查发现一个有证据的问题
→ 生成 ChangeRequest
→ text-to-cad 在源模型上修改并产生新文件
→ 验证目标约束和必须保持不变的约束
→ 输出修改报告与复审结果
```

---

## 1. 目标与非目标

### 1.1 核心目标一：文件审查

支持三类审查，并在输出中明确区分：

| 类型 | 回答的问题 | 示例 |
|---|---|---|
| 文件健康审查 | 文件是否完整、可读、适合下游使用 | 解析失败、单位缺失、实体跳过、PMI 无法关联 |
| 需求符合性审查 | 是否满足当前项目或客户要求 | 外形限制、指定孔径、必需属性、命名规范 |
| 设计/工艺规则审查 | 在特定材料、工艺和标准下是否满足规则 | 企业设计规范、特定工艺的已验证规则 |

审查结果必须包括证据、规则来源、适用条件和无法检查的项目，不能只输出“通过/不通过”。

### 1.2 核心目标二：可验证的文件修改

本项目不自研 CAD 编辑器，也不直接覆盖源文件。

本项目负责：

- 从审查结论或用户意图生成结构化修改请求。
- 绑定源文件版本和目标实体。
- 描述目标约束、保持不变的约束及验收检查。
- 通过外部 skill 交接衔接 text-to-cad，不在本项目内嵌其运行时。
- 对修改产生的新文件重新解析、检查和复审。

优先支持**有源脚本或参数化模型的修改**。只有导入 STEP/B-rep 时，不声称恢复了原始特征树或设计意图，只支持经过单独验证的操作，或仅输出修改建议。

### 1.3 核心目标三：下游任务的数据准备

从设计文件中提取下游任务需要的、与文件本身有关的数据：

- 装配树、零件定义、实例和数量。
- 零件号、名称、材料等已声明属性。
- 几何、特征、尺寸、公差及其证据。
- 数据缺口和下游仍需补充的输入。

输出可以是模型 BOM 或工艺卡输入数据，但不承诺仅凭设计文件生成可直接投产或入库的最终业务文档。

### 1.4 明确不放入本 skill 的能力

以下内容属于外部系统或后续独立项目，本项目不实现连接器、同步逻辑或内置主数据：

- ERP、PLM、PDM、MES、CAPP 的写入或双向同步。
- 企业物料主数据、库存、价格、供应商和成本数据。
- 工艺卡模板管理、排版和最终文档渲染。
- 企业设备、刀具、夹具、工时和切削参数数据库。
- 审批流、权限系统、任务调度和生产下达。
- 自动将工艺草案视为已批准工艺文件。

允许调用方通过显式参数或本地 JSON/YAML 提供少量任务上下文；未提供时记录 `missing_inputs`，不联网补全、不猜测。

### 1.5 其他非目标

- 不自研几何内核、通用特征识别算法或 CAD 格式规范。
- 不做 FEA、CAM 刀路或加工参数求解。
- 不让 VLM 从图片读取尺寸、公差等精确数值。
- 不为了追求格式数量而输出语义严重受损的“统一结果”。

---

## 2. 不可妥协的设计原则

### 2.1 复用成熟项目，不重复造轮子

B-rep 几何计算交给 OCCT，网格等其他表示交给对应的成熟领域库，格式解析交给各自成熟库，修改执行交给 text-to-cad 等工具。

本项目自己实现的是：

- 领域模型和版本化数据契约。
- 解析、测量、审查、修改交接和验证的编排。
- 证据引用、单位、诊断和覆盖率。
- 可执行规则及其评估逻辑。
- 面向 agent 的任务路由。

“薄壳”不意味着代码行数必然很少。**归一化、规则适用性、实体关联和验证本身就是需要认真测试的实现，不能用 600–800 行作为正确性的替代指标。**

### 2.2 事实、判断、推断和工作产品分离

| 对象 | 含义 | 是否可进入 FactSet |
|---|---|---|
| `Fact` | 文件声明、确定性测量或确定性派生结果 | 是 |
| `Finding` | 根据规则得到的合规判断 | 否，进入 ReviewReport |
| `Inference` | ML/LLM/VLM 的概率性解释 | 否，单独记录 |
| `ChangeRequest` | 希望发生的修改 | 否 |
| `WorkProduct` | BOM、工艺卡输入等下游产物 | 否 |

### 2.3 证据优先于结论

每条测量和派生事实都应能回答：

- 来自哪个文件版本？
- 作用于哪个实体？
- 使用什么库、方法和参数？
- 使用什么单位和坐标系？
- 是否完整解析，是否发生降级？

审查结论还必须指向具体规则和事实，而不是只给自然语言判断。

### 2.4 允许“不知道”，并公开覆盖率

空数组不能同时表示“没有”和“没有读到”。缺失、解析失败、不适用和不支持必须具有不同语义。

审查报告必须公开：

- 检查了多少对象。
- 多少规则因缺少数据而无法执行。
- 哪些实体或文件区域被跳过。
- 哪些结论依赖用户提供的上下文。

### 2.5 源文件不可变，修改产生新版本

所有读取、审查、修改请求和下游产物都绑定源文件 SHA-256。修改永不覆盖原文件，并产生新的 `SourceArtifact` 和完整的验证报告。可编辑源和导出物都遵循 copy-on-write：text-to-cad 只修改工作区中的源副本，生成新的源版本、SourceManifest 和导出物。

### 2.6 默认本地、确定性和无 AI 依赖

事实提取、规则执行、BOM 展开和修改验证不依赖模型或网络。LLM 用于需求澄清、规则草案、修改意图整理和结果解释，不参与精确数值的生成。

---

## 3. 开源生态与复用策略

以下判断基于 2026-11-13 对官方仓库和文档的重新核查。项目自报的测试结果仍需在本项目语料上复现。

| 项目 | 已具备的能力 | 本项目怎么用 |
|---|---|---|
| [OCCT / cadquery-ocp](https://github.com/CadQuery/OCP) | B-rep、拓扑、质量属性、距离、射线、XCAF、STEP/IGES | 几何与装配解析底座，不自研几何算法 |
| [cad-mcp-server](https://github.com/ottonic/cad-mcp-server) | 只读 STEP 检查、测量、PMI、revision 引用、diff | 直接竞品和基准；复用其设计经验，比较输出与测试，避免重复造同一工具 |
| [cadtokens](https://github.com/Giltsch/cadtokens) | AP242 语义 PMI、面/边关联、NIST 测试、MCP | 优先评估复用或上游共建；作为 PMI 探测和对照路径 |
| [text-to-cad](https://github.com/earthtojake/text-to-cad) | build123d/OCCT 建模、修改、检查、工程图等 | 修改执行器；通过 ChangeRequest 适配，不在本项目重写建模能力 |
| [ezdxf](https://ezdxf.readthedocs.io) | DXF 实体、块、标注、单位等 | 当前 2D 图纸解析器；recovery/audit、结构目录和有限二维事实 |
| ODA File Converter | 本地 DWG 到 DXF 转换 | 当前可选 DWG 转换器；用户单独安装，不捆绑、不自动下载，记录派生 DXF 和转换器身份；非会员许可限制必须公开 |
| [go-cad](https://github.com/unitedrhino/go-cad) | DWG/DXF 解析、JSON、渲染；项目自报真实图纸测试 | 后续 DWG 候选路径，先独立验证；当前不假设其适合作为核心依赖 |
| [LibreDWG](https://github.com/LibreDWG/libredwg) | DWG 读取、DXF/JSON 转换 | 可选外部程序；必须显示转换降级和许可信息 |
| [IfcOpenShell](https://docs.ifcopenshell.org) | IFC 对象、关系、属性和几何 | 后续 IFC 任务的解析底座 |
| [trimesh](https://github.com/mikedh/trimesh) | 网格加载、拓扑和几何统计 | 后续网格任务的解析底座 |
| [NIST/CAx-IF 测试模型](https://www.mbx-if.org/home/cax/resources) | AP242/AP203、图形/语义 PMI、不同测试类型 | PMI 和几何验证语料，不再以“拿不到第三方样本”为前提 |

还需要参考 BRepNet、UV-Net、AAGNet 等特征识别工作，但第一版不引入训练模型。规则识别必须先证明在目标语料上的准确性，否则只输出候选解释。

### 差异化不再表述为“唯一统一 IR”

cad-mcp-server 已覆盖只读 STEP 检查和证据引用；ODA MCP 已提供商业的跨格式公共 JSON schema；Speckle 等平台也有多格式对象模型。

本项目的合理差异是：

- 开放、轻量、本地、默认无 AI 依赖。
- 将事实、审查、修改交接和修改后验证连成闭环。
- 规则、证据、覆盖率和验证语料是一等交付物。
- 下游只依赖中立结构化数据，不绑定特定 ERP/CAPP 系统。

---

## 4. 总体架构

```text
SourceArtifact
  │  不可变文件、SHA-256、格式和元数据
  ▼
ModelSnapshot
  │  解析器/参数、实体图、源生 ID、单位、坐标、装配、诊断
  ▼
FactSet
  │  declared / measured / derived facts + evidence
  │
  ├──────────────→ Review
  │                Snapshot diagnostics + FactSet
  │                RequirementBundle + RuleSet + ReviewScope + ReviewContext
  │                → Finding + ReviewReport + coverage
  │                         │
  │                         ▼
  │                ChangeRequest → ChangePlan → ApprovalRecord
  │                         │                   │
  │                         ▼                   ▼
  │                  text-to-cad skill handoff → ExecutionRecord
  │                         │
  │                         ▼
  │                  新 SourceArtifact + 新 SourceManifest
  │                         │
  │                         └→ 重新解析 → 验收检查 → 复审
  │
  └──────────────→ Downstream projections
                   → BOMExtract
                   → ProcessCardInput
                   → missing_inputs / provenance
```

`ModelSnapshot` 可以先作为内部模型，不必立即标准化。对外优先稳定四类契约：

1. `facts-core`
2. `review-report`
3. `change-request`
4. 下游数据契约，如 `bom-extract`、`process-card-input`

不再追求用一个 `facts-ir` 同时表示所有格式、审查结论、修改请求和下游工作产品。

---

## 5. 领域模型与数据契约

### 5.1 SourceArtifact

表示一份不可变文件：

- `sha256`
- `format` 和格式 schema
- 文件元数据
- 来源标识
- 可选的业务设计版本号

业务版本号与内容哈希分开；前者可能缺失或错误，不能替代后者。

对于源模型可编辑的工作流，增加 `SourceManifest`，把可编辑源脚本、参数和依赖锁、text-to-cad/构建配置及生成的 STEP 等产物哈希关联起来。`ChangeRequest` 必须同时明确“用于修改的源版本”和“用于事实对比的导出物版本”；只有导出 STEP 而没有可编辑源时，不能标记为 source-backed 修改。SourceManifest 区分 root 与 derived；derived 清单必须指向准确的父清单和旧源映射，验证器实际核对这些关系，而不是只检查清单是否存在。

### 5.2 ModelSnapshot

一次解析的快照，绑定：

- 源文件哈希。
- 解析器、版本和参数。
- 单位与坐标系统。
- 实体及其关系。
- 解析覆盖率和诊断。

实体引用同时保留：

- 源生标识：STEP entity、DXF handle、IFC GlobalId 等。
- 快照内部标识：仅保证当前快照和解析配置下的引用一致性。

不承诺 `F7` 在跨解析器、跨平台或跨修改后仍指向同一几何对象。

### 5.3 Fact

只允许三种确定性事实：

| 类型 | 含义 | 示例 |
|---|---|---|
| `declared` | 文件明确声明 | “文件声明材料为 6061” |
| `measured` | 通过几何内核测量 | “该 body 体积为 17591.5 mm³” |
| `derived` | 由确定性逻辑派生 | “该零件定义有 4 个装配实例” |

示意结构：

```jsonc
{
  "kind": "measured",
  "subject": "body:b1",
  "predicate": "volume",
  "value": 17591.5,
  "unit": "mm^3",
  "evidence": {
    "artifact_sha256": "…",
    "source_entities": ["…"]
  },
  "method": {
    "library": "OCCT",
    "name": "BRepGProp",
    "version": "…",
    "parameters": {}
  }
}
```

Fact 只在取得明确声明或确定性数值时创建。未获得值、单位未知或提取不完整时使用 `FactGap`；FactSet 同时包含 `facts[]` 和 `gaps[]`，不创建值为 null 的“未知事实”。

LLM/VLM 输出不进入 FactSet。未被验证的孔、槽、圆角等识别结果使用 `FeatureCandidate` 或 `Inference`，不能附带未经校准的 `confidence: 0.95` 冒充事实。

### 5.4 Requirement、Rule 和 RuleSet

- `Requirement`：需求或标准原始要求，保留来源和条款。
- `RequirementBundle`：一次审查实际使用的不可变需求集合，固定原文、来源和内容哈希。
- `Rule`：对需求的可执行解释，包含适用条件、输入、阈值、容差、例外和缺失数据处理。
- `RuleSet`：一组有版本、适用领域和验证记录的规则。
- `ReviewScope`：明确本次选择的规则、对象、必需输入和发现范围；实际候选清单与覆盖结果属于报告。

LLM 可以协助生成规则草案，但规则进入正式 RuleSet 前需要明确审核。优先使用“命名检查器 + 参数”的声明式规则，不执行模型生成的任意代码。

### 5.5 Finding 与 ReviewReport

每条 Finding 至少包含：

- `rule_id` 和 RuleSet 版本。
- `subject` 和相关实体。
- `status`：`satisfied` / `violated` / `unknown` / `not_applicable`。
- 支撑或反驳它的事实。
- 严重级别和说明。
- 缺少的输入或能力。

ReviewRun 固定完整快照、FactSet、RequirementBundle、RuleSet、ReviewScope、ReviewContext 和审查器版本。ReviewReport 额外包含规则覆盖率、实体覆盖率、诊断和审查上下文。覆盖率使用统一定义，不能只给出一个掩盖未知项的总分：

- 审查项是“规则 × 候选对象”的一次评估；文件级规则以整个文件为对象。
- `rule_coverage = (satisfied + violated) / evaluations_requiring_decision`。`unknown` 和未知适用性留在分母中且不计为已覆盖；`not_applicable` 单独计数并记录原因。
- 只有不存在 unknown、所有需要判断的评估已得到 satisfied/violated、必需输入已解析且无阻断诊断的实体才是 fully inspected；violated 仍可以是完整检查。全部规则均 not_applicable 的实体不进入分母，适用性 unknown 的实体必须留在分母。
- 发现完整时，`entity_coverage = fully_inspected / decision_required_entities`。发现为 partial 或 unknown 时，真实总覆盖率为 unknown，只能另报明确命名的 discovered-only 比例，不能宣称 100% 总覆盖。
- 实体级规则没有候选对象、必需比较未执行或发现不完整时，不得给出 `compliant_for_scope`。已发现 violated 也不表示其余审查已经完成。

报告同时输出各项计数和比例，避免不同文件用不同分母制造不可比的百分比。

### 5.6 ChangeRequest、ChangePlan 与 ModificationReport

`ChangeRequest` 与具体执行器无关，包含：

- `base_artifact_sha256` 及固定的基线 ModelSnapshot、FactSet 和验证 profile。
- `source_manifest`：source-backed 修改时必填，绑定可编辑源、参数/依赖和生成物；几何级修改时明确为空。
- 来源血缘：review_derived 修改绑定原 ReviewRun、Finding、RuleSet、ReviewScope 和 ReviewContext；user_intended 修改不伪造原审查。
- 目标实体或目标选择条件。
- 修改意图和目标约束。
- 必须保持不变的内容。
- 前置事实条件。
- 验收检查及修改比较容差。
- 输出格式和保存位置约束。

`ChangePlan` 是面向 text-to-cad 等具体执行器的实现计划，固定目标映射、操作、受控载荷、比较方法和容差。`ApprovalRecord` 只批准特定完整请求、计划、基线和执行器配置；任一变化都使批准失效。

`ExecutionRecord` 区分适配器直接观察和外部执行声明，记录实际计划、输入、新源、新导出物和新 SourceManifest。缺少记录时只能标记执行来源为 unattested，不能从新文件的出现推断批准计划已被执行。

`ModificationReport` 分别记录输出验证状态和执行来源状态。输出验证为 `passed` / `failed` / `incomplete`；已知失败优先于 incomplete，任何必需实体无法匹配、必要事实为 unknown、发现不完整或 profile 不兼容时都不得 passed。`passed` 不等于执行来源已证明，后者另为 `attested` / `unattested` / `contradicted`。

### 5.7 WorkProduct

下游产物统一携带：

- 输入文件版本。
- 使用了哪些事实和规则。
- 用户提供的上下文。
- 假设、缺失字段和人工确认状态。

BOMExtract 和 ProcessCardInput 都是 WorkProduct，而不是源文件事实。

---

## 6. 工作流一：文件审查

### 6.1 审查上下文

设计和工艺审查必须显式获得适用的 `ReviewContext`，例如：

- 零件或装配类型。
- 材料和制造工艺。
- 项目/客户要求。
- 适用标准及版本。
- 允许的例外和容差。

缺少上下文时返回 `unknown` 或缩小审查范围，不能套用通用阈值制造确定性假象。

### 6.2 审查执行

```text
读取 ModelSnapshot、FactSet、需求与上下文
→ 确认适用 RuleSet
→ 提取规则需要的事实和快照诊断
→ 执行确定性检查
→ 输出 Finding
→ 汇总覆盖率、未知项和诊断
```

文件健康规则直接消费 ModelSnapshot 中的解析失败、跳过实体和关联失败等诊断；即使 FactSet 为空，也能对解析失败作出审查。其他规则只消费已定义的事实和上下文。无法获得输入时，不允许将检查器异常或空列表当作通过。

### 6.3 审查报告的最小验收要求

- 每个 violated/satisfied 都有规则和证据。
- 每个 unknown 都说明缺少什么。
- 报告区分文件健康、需求符合性和工艺规则。
- 明确“本次没有检查什么”。
- 相同文件、解析器/内核与规则实现版本、参数、规则包和上下文应产生相同的语义结果；数值按声明容差比较，不承诺跨平台位级一致。

---

## 7. 工作流二：可验证修改

### 7.1 修改闭环

```text
Finding / 用户意图
→ ChangeRequest（固定基线快照、FactSet 和 profile）
→ 目标与前置条件检查
→ ChangePlan
→ ApprovalRecord
→ text-to-cad 执行
→ 新源 + 新 SourceManifest + 新文件 + ExecutionRecord
→ 重新解析
→ 验收检查 + 非目标变化检查
→ 按原规则与上下文复审
→ ModificationReport（输出验证与执行来源分列）
```

旧文件哈希不匹配时停止执行，防止把旧实体引用应用到新版本。

### 7.2 目标实体交接

不能假设本项目的 `F7` 可以直接传给 text-to-cad。适配器需要：

- 使用执行器自己的原生引用；或
- 使用几何签名、装配路径和选择条件定位；并
- 在执行前验证目标的前置事实。

目标定位失败时停止，而不是选择“最像”的对象继续修改。

### 7.3 两种修改来源

| 来源 | 支持策略 |
|---|---|
| text-to-cad/build123d 源脚本或可编辑参数化模型 | 通过 SourceManifest 同时绑定源版本与导出物；优先支持，保留参数关系和设计意图 |
| 只有导入 STEP/B-rep | 只支持单独验证过的几何操作；明确历史、PMI 和引用可能丢失 |

不能声称从交换格式自动恢复了原始设计树。

### 7.4 修改后的验证

至少检查：

- 目标约束是否满足。
- 必须保持不变的约束是否仍满足。
- 是否产生非预期体积、拓扑或装配变化。
- PMI、材料、名称和其他元数据是否保留。
- 原审查规则是否通过。
- 原文件是否保持不变。

P2 的前后比较默认使用相同解析/提取 profile；profile 不兼容时不能通过必需比较。修改验收和保持项使用 ChangePlan 固定的比较容差，原规则复审仍使用原 RuleSet 自己的阈值和容差，二者不得互相替代。

### 7.5 修改前后的比较语义

修改验证不能依赖修改前的 `F7` 在新文件中仍表示同一对象。ChangePlan 必须为每项验收检查定义匹配方法和数值容差：

- 文档级体积、面积、计数和已声明属性直接按定义比较。
- 优先使用源生持久标识、源模型操作映射和装配路径匹配实体。
- 几何签名只能作为带容差的辅助证据，不能单独证明跨版本身份。
- 预期拓扑变化必须在 ChangeRequest 中明确；非目标实体的意外新增、丢失或无法匹配必须被报告。
- 无法建立可靠对应关系时，相关检查为 unknown、整体验证为 incomplete；只有已证明应保持的对象确实丢失等已知失败才判 failed。
- 新旧文件哈希相同只表示 `change_observed=no_change`，仍需按验收与保持项判定 passed/failed/incomplete，不能仅凭哈希判断 no-op 是否成功。

---

## 8. 工作流三：下游数据准备

### 8.1 BOMExtract

第一版下游能力优先选择 BOM，因为它主要依赖装配和已声明属性，确定性相对较高。

需要正确区分：

- 零件定义与装配实例。
- 数量与唯一几何体数量。
- 子装配展开和层级。
- 零件号、名称、材料等已声明值与缺失值。
- 每行对应的 occurrence IDs 和来源版本。

不通过“遍历 solids 后按名称计数”生成 BOM。`quantity` 必须与 `quantity_state` 一起解释：只有完整发现和无阻断结构诊断时为 `known`；对账不一致或不完整发现时为 `observed`；相关实例状态未知时为 `unknown` 且数量为空。

输出保持中立，例如：

```text
BOMExtract
  line_items[]
  assembly_links[]
  declared_properties[]
  missing_inputs[]
  provenance
```

它是设计文件侧的数据提取结果，不直接等同于 ERP 中的制造 BOM。

### 8.2 ProcessCardInput

工艺卡需要的外部知识远多于几何。本项目第一阶段只准备设计文件侧的数据：

- 零件和材料声明。
- 几何和经过验证的特征候选。
- 尺寸、公差、表面要求及其关联。
- 关键检验对象。
- 下游仍需补充的输入。

本 skill 不生成工序顺序、装夹方案、设备/刀具选择或加工参数；这些由外部工艺系统或工程师完成。后续若增加工艺推导，应作为独立能力发布，不混入中立的 ProcessCardInput。

不内置：

- 工艺卡模板和排版引擎。
- ERP/CAPP 数据映射和同步。
- 设备、刀具、夹具和工时数据库。
- 自动确定切削参数或生产下达。

### 8.3 外部系统的衔接方式

本 skill 只输出有版本、有证据的结构化 JSON。ERP、PLM、CAPP 或文档系统由调用方读取后自行处理。

这是一种有意的边界：**本项目负责“从设计文件可靠地得到什么”，不负责“企业如何存储、审批和发布它”。**

---

## 9. 模块与 skill 形态

### 9.1 核心模块及接口

| 模块 | 对调用方暴露的主要接口 | 隐藏的复杂性 |
|---|---|---|
| Snapshot | `read(artifact) -> ModelSnapshot` | 格式识别、解析器、单位、装配、诊断 |
| Facts | `extract(snapshot, request) -> FactSet` | 选择性测量、证据和方法记录 |
| Review | `review(ReviewRequest) -> ReviewReport` | 固定完整输入、文件健康诊断、适用性、四态判断、覆盖率 |
| Change | `prepare / plan / verify(VerificationRequest)` | 版本与批准前置条件、执行器交接、输出验证与来源核验 |
| BOM | `extract_bom(snapshot, options) -> BOMExtract` | 装配展开、实例计数、缺失属性 |
| Process data | `prepare(facts, context) -> ProcessCardInput` | 特征/PMI 组织、外部输入缺口 |
| Target resolution | `resolve_target(snapshot, selector) -> TargetResolution` | Occurrence 候选、歧义、显式空间关系、世界坐标放置与发现完整性 |
| Bounded features | `recognize_features(snapshot, query) -> FeatureRecognitionReport` | 名称候选、保守圆柱通孔验证、几何与通用覆盖缺口 |
| Orientation | `infer_orientation(snapshot, selector, policy) -> OrientationReport` | 六向投影、外向启发式、歧义与假设正面 |
| Questions | `answer_question(snapshot, spec) -> AnswerReport` | 多解释、证据策略、数量状态、几何、假设与缺口聚合 |
| Model views | `render_step_svg(snapshot, occurrence_id, view)` | OCCT 隐藏线投影、曲线离散、SVG 与来源清单 |

修改执行需要经过显式批准，不由普通读取或审查命令隐式触发。

### 9.2 SKILL.md 的职责

仓库保持一个 Python 包、一个插件和共享确定性核心，按工作流提供两个已实现 skill：

- `cad-to-facts` 负责事实、证据问答、目标解析、审查、BOM、修改准备和验证。自然语言问题先区分
  直接证据查询、目标指代、规则判断、物理性能问题和修改意图，不能把所有问题都交给渲染或猜测。
  agent 将复合问题拆成显式子意图，依据 AnswerReport 状态/缺口推进证据循环，必要时给出精确目标
  的条件回答或提出决策相关追问；最终按数值、候选、假设和缺口融合答案，不向 CLI 引入通用 NLP。
  DWG/DXF 图纸问题使用独立的 DrawingQuestionSpec profile，回答实体/文字/图层/块/测量/尺寸/
  名称候选/语义证据/显式属性 BOM 等有界事实；语义证据可带出 INSERT 附着的 ATTRIB 声明值，但仍
  属于未验证上下文，不复用 STEP Occurrence 语义，也不把原始实体数或名称候选当作工程语义总数。
- `cad-view` 负责显式 STEP Occurrence 的确定性技术视图和文档插图，输出 SVG 与 ViewRenderManifest。
  它不读取像素尺寸，不把全局相机预设当成设计正面，也不产生视觉推断。

未来可选的 `cad-visual` 只表示尚未实现的独立 VLM Inference 工作流，默认关闭；不得把它写成现有
能力。不新增 Word/PDF/PPT 排版 skill，文档工具消费本项目的中立 JSON 和图片 WorkProduct。

两个 skill 都按用户意图路由，而不是仅按格式路由：

- 检查文件是否完整。
- 根据需求审查。
- 准备修改请求。
- 调用 text-to-cad 并验证结果。
- 提取 BOM 数据。
- 准备工艺卡输入数据。

数值计算、规则评估、版本检查和验证放在可测试的代码中；skill 文档负责收集上下文、选择工作流和解释结果。

### 9.3 当前 CLI 与规划命令

`inspect`、`query`、`resolve`、`features`、`orient`、`ask`、drawing/STEP `render`、`review`、`prepare-change`、`verify-change`、`bom`、`pmi`、受限单 solid `process-input` 和环境诊断 `doctor` 已有实现，当前配置输入为 JSON：

```bash
facts inspect part.step
facts resolve assembly.step --selector examples/resolve-door.json
facts features assembly.step --query examples/features-doors-windows-holes.json
facts orient assembly.step --selector examples/orient-right-door.json
facts ask assembly.step --question "左侧的门在哪里？"
facts ask assembly.step --spec examples/question-door-candidates.json
facts render assembly.step --target occurrence:0 --view-spec examples/view-front.json --output root-front.svg
facts render drawing.dxf --output drawing.svg
facts review part.step --requirements examples/requirements.json --rules examples/rules.json --scope examples/review-scope.json --context examples/review-context.json
facts prepare-change --report review.json --finding finding-1 --before old.step \
  --requirements requirements.json --rules rules.json --scope scope.json --context context.json \
  --spec prepare-spec.json --before-manifest old-manifest.json
facts verify-change --request change.json --before old.step --after new.step
facts verify-change --request change.json --plan plan.json \
  --approval approval.json --execution execution.json \
  --before-manifest old-manifest.json --after-manifest new-manifest.json \
  --origin-review review.json --before old.step --after new.step
facts bom assembly.step --require-property name
facts pmi part.step
facts process-input examples/box.step --context examples/machining-context.json
facts doctor --check
```

`prepare-change` 当前只从 `numeric.compare` 的 violated/unknown Finding 派生目标；`verify-change` 不执行 CAD 或源脚本。`facts review` 不把 RequirementBundle 隐式当作可执行 RuleSet，也不使用未纳入 ReviewRun 身份的默认 ReviewScope。`--origin-review` 仅用于 review_derived 修改；省略批准/执行记录时仍可独立验证输出，但执行来源必须为 unattested。

`pmi` 当前实现受限 AP242 语义 PMI 提取：以 XCAF GD&T 投影读取声明尺寸、几何公差和基准，保留单位、修饰符、基准引用、快照级几何链接、原始实体清单、覆盖率和明确缺口；不创建 Fact，不推断缺失标注或公差符号，不声称完整 AP242 一致性。该结果尚未投影到 `process-input` 或审查规则。

`process-input` 当前只实现恰好一个 STEP solid 的体积、面积、包围盒和显式用户上下文投影；材料声明、PMI 投影和已验证特征仍为 UNSUPPORTED 缺口，不能据此生成工艺规划。`doctor --check` 不解析 CAD，不搜索或启动 ODA。

`resolve` 处理显式 Occurrence/定义/别名/根节点字段及有界空间关系，把唯一、歧义、未解析和读取
失败分开；空间关系使用显式相机和唯一参考，普通参考歧义时不能任选目标，单独 is_root 参考表示
装配根包围盒并集。嵌套候选包围盒位于世界坐标，快照 ID 不是持久身份或源码位置。`features` 只把
门窗名称作为 unvalidated 候选，并验证保守完整圆柱通孔，通用特征覆盖保持 unknown。`orient` 以
最大包围盒投影面及相对装配中心向外生成 assumed 正面，歧义时不推荐。`ask` 用 QuestionSpec /
AnswerReport 统一显式 agent/user 解释和受限离线中英文语法，保留计数状态、几何、假设和缺口；
不支持的语句不得猜测。DWG/DXF `ask` 使用独立的 `DrawingQuestionSpec` / `DrawingAnswerReport`，
执行实体计数/查找、文字查找、图层/块清单、长度/面积/周长汇总、声明尺寸、名称候选、声明语义证据
和显式属性 BOM 查询；语义证据按块名/图层名/文字/属性 tag 匹配并可带出 INSERT 附着的 ATTRIB 值，
但固定为未验证上下文而非推断字段。容器作用域与 off/frozen 图层策略必须显式，
known/partial/unknown/candidate 状态不得混用，失败或无单位测量不得变成零。图纸自然语言语法、通用
图纸语义、标题栏推断、尺寸-几何关联和 INSERT 几何展开尚未实现。STEP `render` 对一个活动
Occurrence 使用 OCCT HLR，生成 new-only SVG 和 ViewRenderManifest。完整契约见
`docs/model-views.md`、`docs/model-questions.md` 和 `docs/drawing-questions.md`。面/边/通用特征
选择器、源声明或功能正面识别、通用 NLP、PNG、照片级渲染和 VLM 问答尚未实现。

`facts inspect --limit` 限制测量实体数，`--summary` 提供摘要，图纸另有 `query` 分页；大装配和网格的选择性查询、分页和输出限制随对应格式支持实现，避免把全部面/边直接塞给 agent。

### 9.4 建议目录

```text
cad-to-facts/
├── SKILL.md
├── pyproject.toml
├── src/cad_to_facts/
│   ├── domain/              # Artifact、Fact、Finding、ChangeRequest 等
│   ├── adapters/            # OCCT、cadtokens 等格式/语义适配器
│   ├── review/              # 规则、上下文、审查执行
│   ├── change/              # 修改请求、交接与验证
│   └── downstream/          # BOMExtract、ProcessCardInput
├── schemas/                 # 按输出类型分别版本化
├── rules/                   # 有来源和版本的规则包
├── tests/
│   ├── fixtures/
│   ├── corpus/              # 下载清单、哈希和预期结果
│   └── workflows/           # 审查、修改闭环、BOM 等端到端测试
└── references/
```

不为控制代码行数而压缩领域边界，也不提前引入图数据库或外部服务。早期使用 JSON 和内存索引即可，规模需求出现后再选择存储实现。

---

## 10. 准确性与验证策略

### 10.1 验证语料是核心资产

至少建立以下层次：

1. 有解析解的简单零件：验证体积、面积、包围盒和距离。
2. NIST CTC/FTC/STC：验证 AP242 PMI、单位、基准和几何关联。
3. 不同 CAD 系统导出的真实 STEP：验证兼容性和降级。
4. 英寸/毫米、装配实例、NURBS、开放 shell 和损坏文件。
5. 审查、修改和 BOM 的端到端任务集。

自写 STEP 再自读只能作为回归测试，不能作为第三方兼容性的证明。

### 10.2 几何与特征的表述必须准确

- `BRepExtrema_DistShapeShape` 的结果称为面/形状最小距离，不能直接等同于通用壁厚。
- 通用壁厚、孔/盲孔、圆角和型腔识别需要独立验证。
- 在验证前输出圆柱面、相邻关系等确定事实，特征只作为候选。
- `valid: true` 必须记录检查器、版本和范围；OCCT 官方也说明 BRepCheck 有效性不是下游正确性的充分保证。

### 10.3 各工作流的验收指标

| 工作流 | 核心指标 |
|---|---|
| 解析 | 数值误差、单位正确性、重复解析一致性、静默遗漏数 |
| 审查 | 误判通过数、误报数、unknown 比例、规则/实体覆盖率 |
| 修改 | 验收通过率、非目标变化、旧版本拒绝、源文件不变、数据丢失 |
| BOM | 行项目和数量准确率、实例追溯、缺失属性标记 |
| 工艺数据 | 特征/PMI 覆盖率、无依据断言数、缺失输入完整性 |

不能只用“文件能打开”或“JSON 能通过 schema”证明工业可用性。JSON Schema 验证结构，语义不变量还需要专门测试。

### 10.4 与现有工具对照

同一批文件和问题至少与 cad-mcp-server、cadtokens 或另一条独立实现对照。差异必须能够解释为：

- 本项目错误。
- 对照工具错误。
- 两者定义或适用范围不同。

不能仅通过比较两个实现都调用了 OCCT 就认定结果独立可信。

---

## 11. 可选视觉能力

视觉能力不是第一阶段依赖，默认关闭。

保留三条约束：

1. VLM 不读取尺寸、公差和粗糙度等精确数值。
2. 视觉结果只进入 `Inference` 或 `diagnostics.visual_check`，不进入 FactSet，不覆盖确定性测量。
3. 只有独立验证集证明其在特定任务上有收益且误报可接受，才纳入正式工作流。

它更适合辅助判断视图类型、标题栏区域或提示人工复核，而不是验证 OCCT 的数值。

---

## 12. 依赖、许可与安全

### 12.1 依赖策略

初始 STEP 路线使用 `cadquery-ocp`；cadtokens 等路径先做概念验证和兼容性测试。当前 DXF 图纸工作流使用 `ezdxf`；DWG 通过用户单独安装的 ODA File Converter 在本地转换为派生 DXF 后进入同一解析路径，ODA 不是 Python 依赖，也不随项目捆绑或自动安装。IFC、网格依赖只在对应工作流启动后引入，避免基础安装承载全部格式。

依赖版本、解析参数和适配器版本写入快照与报告，保证结果可复现。

### 12.2 许可边界

代码仍可选择 MIT，并维护 `THIRD_PARTY_NOTICES.md`。但文档不再使用“Python import 一定无义务”或“subprocess 一定构成 mere aggregation”等绝对表述，实际义务按链接、通信和分发方式审查。

DWG 需要额外注意：

- ODA File Converter 官方说明非会员仅限非商业应用，不能简单写成工业场景的默认免费方案。
- LibreDWG 是 GPL-3.0，且官方说明部分高级对象会跳过、转换覆盖有限。
- go-cad 是 Apache-2.0 候选，但需要独立验证和可接受的安装形态。

任何 DWG 转换都必须记录转换器、版本、源/目标版本、跳过实体和降级状态。

### 12.3 不可信文件与资源限制

只读只消除源文件被修改的一类风险，不等于安全。解析器和外部转换器仍需面对：

- 恶意或损坏文件。
- text-to-cad/build123d 源脚本属于可执行代码，必须经过批准并在隔离环境运行，不能因它是“源模型”就默认信任。
- 原生库崩溃。
- 超大文件和内存耗尽。
- 压缩包与临时文件。
- 外部程序路径和参数安全。
- 结构化输出泄露设计信息。

本地处理默认开启；设置文件大小、时间和内存限制，外部转换使用独立临时目录，不默认上传文件或结果。

---

## 13. 分阶段实施

不再按“格式补全”排期，而按可验证任务纵向推进。

### P0：基线与语料

- 实测 cad-mcp-server、cadtokens 和 text-to-cad。
- 确定首批工程任务和输出契约。
- 建立解析解样本、NIST 样本和真实文件清单。
- 验证 STEP 单位、装配、PMI 和实体引用的基本假设。

### P1：STEP 事实与需求审查闭环

限定单零件：

- SourceArtifact、ModelSnapshot、FactSet。
- RequirementBundle、ReviewScope、ReviewContext 和版本化 ReviewRun。
- 文件健康、单位、拓扑、质量属性和包围盒。
- 少量明确的需求规则。
- 四态 Finding、证据和覆盖率。
- 不承诺通用壁厚和通用特征识别。

当前额外实现了一个受限的 AP242 语义 PMI 纵向切片：`facts pmi` 从 XCAF GD&T 投影输出声明尺寸、几何公差和基准，保留单位、修饰符、基准引用、快照级几何链接、原始实体清单、覆盖率与明确缺口。它不属于 FactSet，不推断缺失标注、图形标注或公差符号，也不表示完整 AP242 一致性；该结果尚未接入审查规则或 P4 工艺输入。

### P2：text-to-cad 可验证修改闭环

优先支持 text-to-cad/build123d 源模型：

- 修改前后 SourceManifest，绑定源脚本、参数/依赖与导出物。
- ChangeRequest、ChangePlan 和固定验证 profile。
- 版本与目标前置条件。
- ApprovalRecord 绑定完整计划，ExecutionRecord 记录实际执行。
- 新文件验证、非目标变化检查和按原规则复审。
- ModificationReport 分列输出验证和执行来源。

P1 可作为技术预览，P2 是首个完整展示项目差异化价值的版本。当前已实现上述 P2 契约的 STEP 纵向切片、真实 CLI 和确定性记录构建器，但 CAD 执行仍由外部 skill 完成，目标派生目前限于 `numeric.compare`，也尚未覆盖完整工程状态矩阵。早期 smoke 见 `docs/text-to-cad-smoke.md`，保持 `unattested`；另一次真实先批准后执行、再验证的运行见 `docs/attested-change-smoke.md`，结果为 `verification_status=passed`、`execution_provenance=attested`。后者是测试身份的本地执行声明，不是独立密码学证明或生产批准。

### P3：STEP 装配与 BOMExtract

- part definition 与 occurrence。
- 装配树和变换。
- 数量、属性、缺失输入和证据。
- 文档级与实体级差异能力按验证结果逐步加入。

当前已实现 XCAF assembly profile、定义/实例/路径/局部变换/父子链接和 `facts bom` 中立模型 BOM 纵向切片。行项目按 PartDefinition 而非名称合并；数量状态区分 `known / observed / unknown`，coverage 分别计数三种状态，源 PRODUCT/NAUO 与 XCAF 定义/组件对账不一致时只允许 observed，且 BOM 保持 incomplete。真实用户生产装配文件（身份与测量细节不公开）的观察与限制见 `docs/real-corpus.md`；其中一份 AP242 文件是当前唯一的真实 complete BOM 观察，不是制造 BOM 或互操作性结论。抑制语义、任意声明属性提取和跨格式 BOM 尚未完成。

### P4：ProcessCardInput

从简单机加工件开始：

- 只使用已验证的特征和 PMI。
- 输出设计文件侧工艺输入与缺失项。
- 不包含自动工序规划、装夹方案或加工参数。
- 不接 ERP/CAPP，不内置模板或企业数据库。

当前已实现一个受限纵向切片：`facts process-input` 仅接受恰好一个 STEP solid，输出已有体积、面积、包围盒 Fact 和 `user_supplied` 上下文，并以 `missing_inputs` 保留必需上下文缺口及材料声明、PMI 投影、已验证特征的 UNSUPPORTED 状态。语义 PMI 可由独立的 `facts pmi` 提取，但尚未投影为本工作产品的检验特性。它不会选择多 solid 文件中的一个，也不会生成任何制造规划。这不表示完整 P4 已完成；PMI 投影、特征、检验对象和更广泛零件流程仍待实现与验证。

审查规则现可用可选 `review_type` 区分文件健康、需求符合性和设计/工艺规则，并输出类型摘要。`rule-packs/step-file-health/` 是首个有来源、适用范围和验证记录的 readiness-only 包；仍不声称存在通用制造/DFM 规则包。真实 text-to-cad 修改记录及离线重放位于 `examples/change-loop/`，其 attested 状态仅是测试 harness 声明，不是独立密码学证明。

### P5：按任务扩展格式

- 为图纸审查接入 DXF/DWG。当前纵向切片已实现：DXF 由 ezdxf 直接读取，DWG 由可选本地 ODA 转为派生 DXF；保留图层、布局、块、原生 handle 和转换证据，并支持声明事实与有限二维测量，LWPOLYLINE bulge 使用解析弧公式。`inspect --summary`、`query` 提供选择性输出，`render` 生成仅用于审查的新 SVG。XREF 默认不展开，显式根目录下可选择独立 artifact 的 linked 证据或保留子来源/单位的 flatten 内容，并受深度、文件数、字节和时间预算约束。`drawing-bom` 仅按显式属性标签提取块引用 BOM，不推断标题栏或 ACAD_TABLE 语义。`ask` 通过独立 `DrawingQuestionSpec` 回答有界图纸事实，实体计数、文字、图层/块、二维测量、声明尺寸、未验证名称候选、声明语义证据和显式属性 BOM 均保留作用域、单位、状态和缺口；语义证据可带出 INSERT 附着的 ATTRIB 值，但不是推断材料/零件/功能字段。通用图纸语义、标题栏推断、尺寸-几何关联和 INSERT 展开仍不实现。详见 `docs/drawing-analysis.md` 和 `docs/drawing-questions.md`。
- 为建筑对象和工程量任务接入 IFC。
- 为打印或网格质量任务接入 trimesh。
- 每种格式使用公共 envelope 和独立 profile，不强塞进同一组 `bodies/features` 字段。

视觉能力独立评估，不阻塞上述主线。

---

## 14. 交付物与发布策略

核心交付物从单一 schema 调整为：

- 可安装的 agent skill 和本地 CLI。
- 版本化的事实、审查、修改和下游数据契约。
- 有来源、适用范围和验证记录的规则包。
- 解析、审查、修改闭环和 BOM 的测试语料。
- 对 OCCT、cad-mcp-server、cadtokens、text-to-cad 等项目的明确致谢与复用说明。

在只有一个实现和一个消费者时，不急于把所有 schema 独立发包。先通过真实工作流稳定契约，再考虑将成熟的部分作为独立标准发布。

---

## 15. 一句话

**把 B-rep 几何交给 OCCT，把其他表示和格式交给对应的成熟库，把修改交给 text-to-cad；cad-to-facts 自己做好事实、证据、规则、版本和验证，让企业系统在本项目之外消费可靠的数据。**
