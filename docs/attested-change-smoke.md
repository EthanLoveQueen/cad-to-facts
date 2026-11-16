# text-to-cad 已 attest 的修改闭环测试

日期：2026-11-14。该记录补充而不是改写 `docs/text-to-cad-smoke.md`：历史 smoke 仍保持
`execution_provenance=unattested`，本次是在独立工作区重新执行的一次真实本地测试。

## 边界

- 外部执行器为单独安装的 text-to-cad / `cad` 0.11.10；本项目两个 change 命令均未执行 CAD。
- 模型为 10 × 20 × 30 mm 的 build123d 盒子；批准的操作只把独立副本中的 `HEIGHT=30.0`
  改为 `HEIGHT=40.0`。基线源、基线 STEP 和修改后工作区彼此分离。
- 批准者和 attest 者都是测试身份 `cad-to-facts-test-harness`。这是一份一致、可追溯的本地
  执行声明，不是独立密码学证明、工程发布批准或通用执行器互操作性证明。
- 记录构建器只读取实际工作区字节并生成绑定记录；它不执行源脚本，也不会从输出文件自动推断批准或执行。

## 执行顺序

1. 用外部 `cad run model.py` 和 `cad model export ... box.step --json` 生成基线。
2. 以 `read_scope=assembly` 审查基线。text-to-cad 的单盒 STEP 带一个装配包装，显式使用装配 profile
   避免把 single-part 扁平化诊断隐藏掉。
3. 用 `build_root_source_manifest` 从实际字节构建 root SourceManifest，再运行
   `facts prepare-change --read-scope assembly ...` 生成 ChangeRequest 和 ChangePlan。
4. **在修改后执行之前**创建显式测试 ApprovalRecord，绑定完整请求、计划、基线、执行器和 payload。
5. 只修改独立副本中的高度参数，运行外部 CAD 并导出新 STEP。
6. 用 `build_derived_source_manifest` 对实际前后源差异和计划进行核对，构建 derived manifest；
   用 `build_execution_record` 保存显式 `attested_by`、`attestation`、日志引用和时间。
7. 审查新文件并运行完整的 `facts verify-change`，提供 request、plan、approval、execution、
   前后 manifests、origin review 和前后 STEP。

## 绑定身份

```text
ChangePreparation  bbcdd283921f0e2c83706bc3b11f52f017a294251c285fa87408a8a3b6973cfd
ChangeRequest      b3440c4cac5684726b943d8c17ff9ed3912bee1a69eb31a5636265e64f48b9c8
ChangePlan         bd610fa94a94dc19af98f5782485d341bdb78cfe5cf5b19e4deeb68f6b3147f9
root manifest      ac6c6840a3a8b717dee6ca3e81467dd410752b9b9108d51fd8aa02763f3633da
derived manifest   fde6d64c44ebee876b830c21634369c9f252be65283d90253f21415cf114cf89
ApprovalRecord     dea2dfdb8aba970e924ef5885547a9244f247563445a1b7ecea3394dbf43afeb
ExecutionRecord    ba6fb86d0ebff6a6f82b15accd9df7ba7e0a4724d4e196893c7a292061284cae
ModificationReport 2253239725335b21e53d68327c835d8369478032bfe62bee4da75394c4a6a034
```

批准时间为 `2026-11-14T08:10:14Z`，执行声明时间为 `2026-11-14T08:12:42Z`。
基线 STEP SHA-256 为 `f010f94b…0623`，新 STEP 为 `334b5343…b6`；完整值保存在测试工作区的记录中。

## 实际结果

- `verification_status=passed`
- `execution_provenance=attested`
- `change_observed=changed`
- `manifest_validation=passed`
- `approval_validation=passed`
- `unresolved_issues=[]`，`tool_error=false`
- 修改后审查为 `compliant_for_scope`，`complete=true`；目标高度 40 mm、保持项、原规则复审和记录绑定均通过。

该运行证明了一个简单解析模型的完整记录链路可以实际走通；它不覆盖通用源操作、持久跨版本身份、
PMI/特征保留或完整 P2 工程状态矩阵。

## 公开重放

原始绑定 JSON、前后源/STEP/manifest/review 和脱敏 native 日志现收录于
`examples/change-loop/`。其 README 提供完整离线 `facts verify-change` 命令，
`tests/test_golden_change_example.py` 通过公共 CLI 验证 `passed / attested / changed`。
由于证据从原绝对目录移动，重放必须显式使用 `--replay-relocated-output`；报告会说明原绝对
目录未重新验证。该选项不修改任何绑定记录，也不能用于掩盖实时修改的输出位置错误。
原始日志含本地 viewer token，不发布；公开日志为 UTF-8 脱敏副本，原始日志哈希只作为本地
审计引用。补充 native 证据不替代 ExecutionRecord。
