# text-to-cad 外部 skill smoke 测试

日期：2026-11-14。该记录覆盖外部执行交接、正式 ChangeRequest/ChangePlan、root/derived SourceManifest 和新 STEP 输出验证；历史运行没有批准/执行记录，因此不代表已 attest 的批准执行，也不代表完整 P2 工程验证矩阵已经完成。后续独立工作区中重新执行的已 attest 测试见 `docs/attested-change-smoke.md`；它不回填或改变本历史报告的来源状态。

## 环境与边界

- text-to-cad 插件及 `cad` 运行时：0.11.10，Windows 11。
- text-to-cad 使用自己的 Python 3.14/build123d 环境；cad-to-facts 仍使用锁定的 Python 3.13/OCCT 环境。
- text-to-cad 是单独安装的外部 CAD skill，不是本项目的 Python 依赖。
- 遥测与自动更新在测试前关闭；测试命令另设 `DO_NOT_TRACK=1` 和 `CADGEN_UPDATE_CHECK=0`。
- 在独立模型工作目录运行 `cad run`。不要从 cad-to-facts  checkout 根目录运行外部模型：0.11.10 会把当前项目的 `uv.lock` 纳入模型环境，造成不必要且可能不兼容的依赖求解。

官方安装入口：

```bash
claude plugin marketplace add earthtojake/text-to-cad#latest
claude plugin install text-to-cad@earthtojake
# 按官方说明安装 cad 运行时；固定版本可用：
curl -fsSL https://texttocad.dev/install.sh -o install.sh
sh install.sh --only claude --no-telemetry --version 0.11.10
```

## 测试模型与操作

基线和修改后模型分别位于两个独立目录，各自拥有一个 build123d 源脚本。模型为单一盒子，宽 10 mm、深 20 mm；基线 `HEIGHT=30.0`，副本 `HEIGHT=40.0`。没有覆盖基线源或基线 STEP。

外部 skill 使用的实际命令形式：

```bash
cad run model.py
cad model export "$MODEL_ID" box.step --json
```

对两个导出物分别运行：

```bash
facts review box.step \
  --requirements requirements.json --rules rules.json \
  --scope scope.json --context context.json
```

规则只有一个明确断言：`bbox.extent.z >= 40.0 mm`，绝对容差 `1e-7`。

## 实际结果

| 检查 | 基线 | 修改后 |
| --- | --- | --- |
| text-to-cad 构建边界 | 10 × 20 × 30 mm | 10 × 20 × 40 mm |
| STEP 导出 | 成功，17,464 bytes | 成功，17,464 bytes；新文件、新哈希 |
| cad-to-facts 快照 | `ready` | `ready` |
| Z 向包围盒 | 30.0 mm | 40.0 mm |
| 体积 | 6000.0 mm³ | 7999.999999999998 mm³ |
| 表面积 | 2200.0 mm² | 2799.9999999999995 mm² |
| Finding | `violated` | `satisfied` |
| ReviewReport | `non_compliant`, `complete=true` | `compliant_for_scope`, `complete=true` |
| 实体匹配 profile | `adapter_key` | 同一 profile |
| 必需 `solid:0` | — | `matched`，匹配报告 `complete` |

源与产物 SHA-256：

```text
baseline model.py  3c43653e06d7f1934eac622a3d90c5d8963dced8addff0026ca793e258ec541b
baseline box.step  f010f94b122eec53e9f379fd81192f32affd5fcfefef8c5bf780878970cd0623
modified model.py  c234aeb2b098b56f4e2eb0d51e3069cca34eec6b410bd9196fbe02afc337e580
modified box.step  334b53438cd306be33753dda06642279213a515e2dbfec9297a813f3363596b6
```

## 正式准备与输出验证

在上述真实外部导出之后，使用基线原审查报告和显式 `prepare-spec.json` 运行了已实现的命令：

```bash
facts prepare-change \
  --report baseline/review.json --finding <baseline-finding-id> --before baseline/box.step \
  --requirements requirements.json --rules rules.json \
  --scope scope.json --context context.json \
  --spec prepare-spec.json --before-manifest baseline/manifest.json

facts verify-change --request change-request.json --plan change-plan.json \
  --before-manifest baseline/manifest.json --after-manifest modified/manifest.json \
  --origin-review baseline/review.json \
  --before baseline/box.step --after modified/box.step
```

准备规格把 `HEIGHT` 绑定到外部 text-to-cad 0.11.10 执行器，声明 `set_parameter` 操作、40 mm 目标、30 mm 基线前置条件、宽/深保持项、固定 `adapter_key` 匹配 profile，以及禁止覆盖基线的输出策略。准备与验证命令都没有运行源脚本或 CAD；实际 CAD 执行仍是此前单独进行的外部 skill 操作。

前后清单均按实际文件字节验证：baseline 是 root，modified 是 derived，并精确引用 baseline 父清单和旧/新 `model.py` 哈希。正式对象与结果：

```text
baseline manifest   ac6c6840a3a8b717dee6ca3e81467dd410752b9b9108d51fd8aa02763f3633da
modified manifest   fde6d64c44ebee876b830c21634369c9f252be65283d90253f21415cf114cf89
ChangePreparation   cc6fcd09c011365e961548ed900edc7a1e9b5db136e6bf982558971764f38821
ModificationReport  0e452abd72e4f0355369f49fe54b1e5b66af404b6d4730b17420985adbf03f15
after ReviewReport  eed15db3e2165f9c6773a135d0daf519f9978be024a3519be716e901a3c9dcfd
```

`modification-report-current.json` 是更新输出位置、精确源映射和完整原规则复审检查后重新生成的当前报告（早期报告保留在 `modification-report.json`）。实际状态为：

- `verification_status=passed`；目标、前置条件、不变量、非目标比较、固定 profile 和原 Finding 复审均通过。
- `manifest_validation=passed`，`change_observed=changed`，`unresolved_issues=[]`，`tool_error=false`。
- `approval_validation=not_provided`，`execution_provenance=unattested`。没有为历史外部运行倒签或补造 ApprovalRecord/ExecutionRecord。

因此，这次 smoke 证明了“正式准备 + 真实新文件输出验证 + 清单血缘 + 原规则复审”链路，但没有证明被批准的计划实际执行。验证基线 FactSet 与原审查 FactSet 分开绑定；额外的前置/保持项提取没有伪装成原审查输入。

## 尚未证明的内容

- `adapter_key` 匹配只验证同一解析 profile 下的显式遍历键，不证明跨修订持久身份。
- 本次只覆盖一个简单解析几何体和一次外部导出，不能据此宣称通用 STEP 导出器互操作性。
- 本次历史运行没有真实 ApprovalRecord/ExecutionRecord；测试中的一致/矛盾记录不能替代它的执行来源。后续已 attest 的独立重跑见 `docs/attested-change-smoke.md`。
- `prepare-change` 当前只从 `numeric.compare` 的 violated/unknown Finding 派生目标；其他修改意图需要显式请求或后续实现。
- 通用特征/PMI/装配保留、更多源操作和完整 P2 状态矩阵仍需独立验证。BOM 已有独立实现和真实装配观察记录；process-input 仍未实现。
