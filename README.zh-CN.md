# pvm：有原文证据的论文科普视频

<!-- repository-catalog:start -->
**分类：视频创作与剪辑** · [同类仓库](https://github.com/instl999?tab=repositories&q=topic%3Avideo-creation)

把研究论文与口播文案制作成纸片拼贴科普视频，逐条检查研究陈述的原文证据。

相关项目：[douyin-carousel-generator](https://github.com/instl999/douyin-carousel-generator) · [douyin-daodaoshou-tool](https://github.com/instl999/douyin-daodaoshou-tool) · [douyin-spongebob-economics-tool](https://github.com/instl999/douyin-spongebob-economics-tool)

[English](README.md)
<!-- repository-catalog:end -->

[English](README.md) | 简体中文

`pvm` 把研究论文和口播文案制作成抖音风格科普视频：开场展示论文，随后用纸片拼贴海报讲解。研究陈述必须能追溯到来源中的逐字原文。

## 安装（Windows）

在仓库目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

脚本创建 `.venv`、安装依赖、下载开放许可字体、从 `.env.example` 创建 `.env`，并运行测试。按需在 `.env` 填入 API 配置。项目数据位于被 Git 忽略的 `projects/`、`research/` 和 `cache/`；可设置 `PVM_HOME` 改变数据位置。

## 制作流程

所有命令使用 `.venv\Scripts\python -m pvm <命令>`。以下以 `sunk-cost` 为例，口播文案放在 `script.txt`：

```powershell
.venv\Scripts\python -m pvm research "sunk cost" -q "sunk cost effect decision making" --since 2000
.venv\Scripts\python -m pvm script sunk-cost --file script.txt
.venv\Scripts\python -m pvm paper sunk-cost --pick sunk-cost:c01
.venv\Scripts\python -m pvm sentences sunk-cost
.venv\Scripts\python -m pvm source sunk-cost --find "sunk cost"
.venv\Scripts\python -m pvm plan sunk-cost --auto
.venv\Scripts\python -m pvm check sunk-cost
.venv\Scripts\python -m pvm review sunk-cost
.venv\Scripts\python -m pvm voice sunk-cost
.venv\Scripts\python -m pvm animatic sunk-cost
.venv\Scripts\python -m pvm images sunk-cost --dry-run
```

先人工核对分镜、研究陈述与预览。确认后生成图片，并在最终渲染前通过严格校验：

```powershell
.venv\Scripts\python -m pvm images sunk-cost
.venv\Scripts\python -m pvm check sunk-cost --strict
.venv\Scripts\python -m pvm render sunk-cost --ratio both
```

`--ratio both` 输出 3:4 和 9:16 成片、封面、描述、manifest 与质检结果。`render --draft` 允许缺失图片用占位图补足，仅适合预览。

## 证据与画面规则

- 事实、解释与建议分开标记。研究事实要引用原文，译文或改写不能充当逐字证据。
- 不把相关性写成因果，不把样本结论扩大到所有人。
- 开场标题也要有证据或解释依据，避免让观众误以为论文支持更强的结论。
- 分镜要覆盖每句口播，文案变更后重新校验锚点。
- 论文展示范围取决于许可；非开放论文不因下载到本地就自动获得公开展示权限。
- 场景中的少量标签由图像模型生成；数字、名字、引用和标题由程序排版。

完整分镜规则见 [`AGENTS.md`](AGENTS.md)，产品规格见 [`docs/spec.md`](docs/spec.md)。

## 服务与费用

`AGENT_PLAN_API_KEY` 可用于项目配置的图片、配音与文本服务；`PVM_LLM_API_KEY` 可改用独立文本 API。配音、规划、审核和生图可能计费，`images --dry-run` 先显示提示词与 AFP 估算。计划额度周期按购买日计算，设置 `PVM_PLAN_START` 后用 `pvm quota` 查看。

缓存、预算记录与 manifest 用于追踪调用和复用结果。具体模型、已验证日期、示例用量和服务限制见 [英文说明中的 Live services](README.md#live-services)，以实际服务配置和账单为准。

## 测试

```powershell
.venv\Scripts\python -m unittest discover -s tests -t .
```
