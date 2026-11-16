# cad-to-facts

cad-to-facts 是围绕设计文件事实、审查、可验证修改和下游数据准备的单一领域上下文。本词汇表固定这些概念的语义，避免把来源事实、工程判断和外部业务数据混用。

## 来源与快照

**SourceArtifact**:
一份不可变的设计或源模型文件，由原始字节的 SHA-256 唯一标识；业务设计版本号只是可选元数据。
_Avoid_: CAD 文件、设计版本、模型版本

**SourceManifest**:
一组可编辑源文件、构建参数与依赖配置及其生成物之间的版本关联。
_Avoid_: 源文件哈希、STEP 哈希、构建清单

**ModelSnapshot**:
某个 SourceArtifact 在指定解析器、版本和参数下得到的一次模型视图；它不是跨解析器或跨版本稳定的通用模型。
_Avoid_: 统一 IR、通用 CAD 模型、源文件

**EntityRef**:
对 ModelSnapshot 中某个实体的限定引用，包含快照身份及可用的源生标识；不承诺跨文件修订有效。
_Avoid_: 持久 ID、全局 ID、稳定面 ID

**DrawingStructure**:
ModelSnapshot 中图纸专用的一次结构视图，保留图层、布局、块和实体容器关系；它不是 STEP 实体或装配结构。
_Avoid_: 通用 bodies/features、图纸 BOM、标题栏语义

**DrawingConversion**:
DWG 主 artifact 与本地产成的派生 DXF 之间的转换证据，记录转换器身份、固定选项和派生字节哈希；它不证明视觉或语义完全等价。
_Avoid_: 新 SourceArtifact 身份、执行证明、无损转换证明

**DrawingExternalReference**:
图纸中一条外部引用边及其解析证据，关联宿主与独立被引用 SourceArtifact、声明路径、嵌套关系和发现状态；链接记录不等于把引用内容并入宿主，展平副本也不改变实际来源。
_Avoid_: 已解析宿主实体、普通块定义、持久装配 Occurrence

**DrawingRender**:
从指定图纸布局派生的视觉审查 WorkProduct，例如带字节哈希的 SVG；它不是视觉保真、几何等价或工程正确性的证明。
_Avoid_: DrawingSnapshot、Fact、视觉测量、渲染认证

**ViewSpecification**:
一次模型视图所采用的明确观察方向、显示方式和图像参数；坐标预设不等于设计语义方向。
_Avoid_: 设计正面声明、工程图模板、视觉推断、持久相机身份

**SemanticViewIntent**:
用户或任务附加给观察方向的外部语义，例如把某个方向称为“正面”；它必须区分用户选择与假设，不能冒充源文件声明。
_Avoid_: 源生方向、设计正面证明、Fact、设计意图声明

**ModelViewRender**:
从 ModelSnapshot 中明确选择的模型范围派生的视觉 WorkProduct；它不是 Fact、几何等价证明或可用于精确测量的图像。
_Avoid_: ModelSnapshot、DrawingRender、Inference、工程图合格证

**ViewRenderManifest**:
一次 ModelViewRender 的来源、目标、视图参数、方法、输出和诊断记录；它证明输出与这些输入的绑定，不证明视觉完整性或设计语义。
_Avoid_: FactSet、ReviewReport、ExecutionRecord、视觉保真证明

## 事实与证据

**Fact**:
关于某个 ModelSnapshot 的已声明、确定性测量或确定性派生陈述；只有取得明确内容时才存在。
_Avoid_: 推断、判断、建议、未知事实

**FactGap**:
某项事实提取未能取得值或完整覆盖时留下的明确缺口，记录原因和所需能力；它不是值为空的 Fact。
_Avoid_: unavailable fact、空事实、零值、空数组

**Evidence**:
支撑 Fact 或其他输出的来源引用与方法信息，包括文件版本、源生实体、解析或计算方法和必要参数。
_Avoid_: 理由、解释、置信度

**Inference**:
由 ML、LLM 或 VLM 产生的概率性解释，不能作为 Fact。
_Avoid_: 视觉事实、AI 测量、推断事实

## 语义 PMI

**SemanticPMI**:
设计文件中与几何关联、机器可解释的尺寸、几何公差、基准和表面纹理等制造信息；它不同于仅用于显示的图形标注，也不等于检验计划或工程正确性结论。
_Avoid_: 图形标注、OCR 文本、检验结果

**PmiAnnotation**:
从设计文件声明的单条语义 PMI（尺寸、几何公差或基准），保留声明值、单位、修饰符、基准引用、几何关联和来源；未取得的值或关联不是零，也不是推断值。
_Avoid_: Fact、特征、检验特性、推断标注

**PmiExtract**:
一次语义 PMI 提取的中立结果，绑定来源快照并包含声明注解、观察清单、覆盖率、缺口和诊断；它不声称完整 AP242 一致性或工程正确性。
_Avoid_: FactSet、ReviewReport、AP242 合格证

**PmiLinkStatus**:
语义 PMI 与几何关联在本次提取中的状态 `resolved / unresolved / absent`；它只描述是否找到并映射了几何，不证明设计意图或跨修订身份。
_Avoid_: 稳定面 ID、持久关联、必然无基准

**PmiGap**:
某条语义 PMI 的值、单位、基准标识或几何关联未能取得时留下的明确缺口；它不同于“文件中没有该标注”。
_Avoid_: 零值、空标注、推断值

## 需求与审查

**Requirement**:
来自用户、项目或标准的原始要求，保留来源和条款；它本身不一定是可执行规则。
_Avoid_: 检查器、规则、阈值

**RequirementBundle**:
一次审查实际使用的不可变需求集合，保留每项需求的原文、条款定位和来源版本。
_Avoid_: 需求文件名、规则集合、临时提示词

**Rule**:
对 Requirement 的一种版本化、可执行解释，具有适用条件、输入、容差和缺失数据语义。
_Avoid_: 需求、提示词、任意脚本

**RuleSet**:
一组具有共同版本、适用范围和验证记录的 Rule。
_Avoid_: 规则提示词、标准全文、规则数据库

**ReviewContext**:
决定规则如何适用的任务上下文，例如产品类型、材料、工艺和项目约束；缺失时不能默认套用通用值。
_Avoid_: 全局配置、用户偏好、企业主数据

**ReviewScope**:
一次审查明确声明要覆盖的规则、对象、必需输入和发现范围；实际发现的候选对象及其覆盖结果属于审查报告。
_Avoid_: 全局配置、已发现实体清单、上下文

**Finding**:
一条 Rule 对一个适用对象的评估结果，状态为 satisfied、violated、unknown 或 not_applicable。
_Avoid_: 事实、错误、警告、缺陷

**ReviewType**:
Rule 和 Finding 的可选审查分类，区分文件健康、需求符合性与设计/工艺规则；分类不改变 Finding 状态、适用范围或完整性。
_Avoid_: 规则来源、严重级别、合规状态、通用制造标准

**ReviewRun**:
由同一组不可变快照、事实、需求、规则、范围、上下文和审查器版本确定的一次审查运行。
_Avoid_: 审查报告、审查结论、审查任务

**ReviewReport**:
一次审查的完整结果，包含 Finding、诊断、上下文、规则与实体覆盖率；没有违规不等于审查完整或产品合格。
_Avoid_: 审查事实、合格证、DFM 结论

## 修改与验证

**ChangeRequest**:
与具体执行器无关的修改意图，绑定修改基线、目标、约束、前置条件和验收检查。
_Avoid_: 修改命令、建模脚本、ChangePlan

**ChangePlan**:
ChangeRequest 面向特定执行器的实现计划，包含目标绑定、执行步骤和比较策略。
_Avoid_: 修改意图、自然语言提示词、通用修改请求

**ChangePreparation**:
由同一修改基线派生并绑定的 ChangeRequest 与 ChangePlan；它只准备外部执行交接，不包含批准或实际执行。
_Avoid_: 执行结果、批准记录、修改报告

**VerificationProfile**:
一次修改前后比较固定采用的解析、事实提取和实体匹配方法及其版本、选项与容差；配置不兼容时相关比较保持未知，不能把差异直接判为修改结果。
_Avoid_: 默认解析配置、跨版本通用模型、实体身份

**ApprovalRecord**:
对特定 ChangeRequest、ChangePlan、修改基线和执行器配置的明确批准；其中任何内容变化都需要重新批准。
_Avoid_: 执行记录、一般用户同意、长期授权

**ExecutionRecord**:
对某次实际执行所用计划、输入、执行器和输出的可追溯声明或直接观察记录；它不同于输出是否符合验收条件。
_Avoid_: 验收报告、批准记录、成功日志、来源事实

**ModificationReport**:
一次修改的输出验证及执行来源结果，验证状态为 passed、failed 或 incomplete；无法完成必要比较时不能通过，通过也不自动证明批准计划已被执行。
_Avoid_: 修改事实、成功日志、复审报告、执行证明

**EntityMatch**:
在明确声明的匹配方法（源生标识、遍历键或数值指纹）和容差下，为基线实体找到候选实体的结果；matched 只表示在该方法下匹配，不证明跨修订持久身份，未匹配结果为 unmatched、ambiguous 或 unresolved。
_Avoid_: 持久身份、同一实体证明、相似度

## 装配与下游工作产品

**PartDefinition**:
装配中可复用的零件或子装配定义；多个 Occurrence 可以引用同一个定义，名称不是定义身份。
_Avoid_: 独立零件副本、零件名称、持久零件号

**Occurrence**:
某个 PartDefinition 在装配中的一次使用，具有父子路径、局部变换和实例状态；它不是唯一几何体数量。
_Avoid_: 零件定义、solid 序号、物料数量

**TargetSelector**:
在一个 ModelSnapshot 内筛选目标 Occurrence 的显式条件集合，可包含声明字段和有界空间约束；它只表达可判定条件，不替用户猜测功能或设计意图。
_Avoid_: 自然语言答案、持久查询、功能特征证明、ChangeRequest

**TargetCandidate**:
符合 TargetSelector 的一个已发现 Occurrence 及其快照内路径、声明名称、状态和位置证据；名称匹配不证明它具备用户所说的功能。
_Avoid_: 已确认零件、持久身份、源变量位置、实体匹配证明

**TargetResolution**:
一次目标解析的结果，区分唯一候选、多个候选、未发现候选和读取失败，并保留发现完整性；歧义时不得任意选定目标。
_Avoid_: 自动消歧、跨修订身份、源码定位、工程不存在证明

**SpatialConstraint**:
在显式相机坐标系和唯一参考对象下，对目标世界包围盒中心投影或包围盒间隙作出的有界空间约束；它不证明接触、包含、精确形状距离或功能关系。
_Avoid_: 自然语言猜测、碰撞证明、精确最小距离、功能语义

**FeatureCandidate**:
由声明名称或有界几何识别方法得到的门、窗或孔候选；名称候选未经验证，几何验证也只覆盖其明确方法，不能推出通用特征覆盖。
_Avoid_: 已确认工程特征、通用特征数量、功能证明、置信度

**OrientationReport**:
根据显式启发式策略生成的方向候选、几何投影数据、歧义诊断和可选假设视图；推荐正面的语义始终是假设，不是源声明或功能正面。
_Avoid_: 设计正面声明、视觉识别、功能方向证明、Fact

**QuestionSpec**:
保留原始问题、解释来源、一个或多个显式解释、假设和解释缺口的问答输入；agent 的自然语言解释不等于 Fact。
_Avoid_: 文件事实、已验证目标、任意自然语言理解证明、ChangeRequest

**AnswerReport**:
按 QuestionSpec 的显式解释返回候选、测量、数量状态、方向假设、证据和缺口的问答结果；complete 只表示所有解释按其证据策略得到回答。
_Avoid_: 通用特征完整性、语义正确性认证、置信度、Finding

**DrawingQuestionSpec**:
面向 DWG/DXF 的独立问答输入，使用实体、图层、容器、块、文字、测量、尺寸、名称候选、语义证据和显式属性 BOM 意图；不复用 STEP Occurrence、特征或方向语义，图纸自然语言语法未实现。
_Avoid_: STEP QuestionSpec 复用、通用图纸语义、标题栏推断、功能特征验证

**DrawingAnswerReport**:
按 DrawingQuestionSpec 返回图纸实体计数/查找、图层/块清单、测量、声明尺寸、未验证名称候选、声明语义证据、显式 BOM、作用域和缺口的问答结果；known/partial/unknown/candidate 区分发现完整性，失败读取或无量纲测量不得变成零。
_Avoid_: 工程语义总数、已验证门窗孔、尺寸-几何关联、持久实体身份

**DrawingSemanticEvidence**:
按块名、图层名、文字或属性 tag 匹配出的声明上下文，可带出 INSERT 附着的 ATTRIB 值；它始终是未验证候选证据，不是推断出的材料、零件或功能字段。
_Avoid_: 语义字段事实、材料推断、功能验证、置信度

**KnownQuantity**:
在装配发现完整且没有未解决结构诊断时，按活动 Occurrence 计算的完整数量；它不是库存、采购或制造 BOM 数量。
_Avoid_: 制造数量、库存数量、采购数量

**ObservedQuantity**:
在装配发现不完整或源记录与解析结构未对账时，实际观察到的活动 Occurrence 数量；它不是已知完整数量。
_Avoid_: 完整 BOM 数量、库存数量、采购数量

**UnknownQuantity**:
至少一个相关 Occurrence 状态未知时的数量状态，数量为空；不能用 observed 数值替代 unknown。
_Avoid_: 零数量、已观察数量、完整数量

**WorkProduct**:
由 Fact、Rule 和显式上下文生成的下游产物，带有来源、假设、缺口和确认状态。
_Avoid_: 文件事实、最终业务记录

**BOMExtract**:
从模型装配结构和已声明属性得到的中立 BOM 数据，不等同于 ERP 中的制造 BOM。
_Avoid_: ERP BOM、制造 BOM、物料主数据

**DrawingBOMExtract**:
按调用方显式指定的属性标签和容器，从图纸块引用及其实例属性得到的中立数量与属性数据；它保留来源和 unknown，不从标题栏位置、文本或块名猜测物料语义。
_Avoid_: BOMExtract、ACAD_TABLE 语义、标题栏推断、制造 BOM

**ProcessCardInput**:
为外部工艺设计准备的零件、几何、PMI、检验对象和缺失输入数据，不包含工序规划或已批准工艺。
_Avoid_: 工艺卡、工艺路线、加工方案、CAPP 工艺文件
