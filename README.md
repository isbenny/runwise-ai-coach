# RunWise AI Coach｜稳跑AI教练

**把你的 AI 助手变成持续使用的跑步教练。** 一个轻量 Agent Skill，复用已验收的 Coach Core 计算规则，通过你自己的手表 MCP 读取数据、分析训练、提出课表与反馈调整。

**固定版本：v0.1.1。** 无稳跑账号注册、云端训练数据库、模型API网关或独立聊天系统。仓库包含必要源码和空模板，不含任何人的训练或凭据。项目自身开源许可尚未指定，见 [LICENSE](LICENSE)；第三方许可仅适用于对应组件。

## WorkBuddy 桌面版

**复制对应手表指令 → 官方导入 Skill → 设置里添加并信任 MCP → 本人授权 → 开始分析。**

WorkBuddy 5.8.3 已实际加载 Skill，读取既有 Garmin 中国区真实记录，并完成 COROS 官方 OAuth 与活动读取；新任务可以重新读取。首次需要官方界面确认，不能仅凭一句提示词自动信任或授权。

[按手表查看 WorkBuddy 最少步骤](references/workbuddy-desktop.md)。已有本人连接优先复用；新安装不继承开发者凭据或训练。

## 佳明用户：复制给你的 AI 助手

**复制安装指令 → AI助手安装稳跑Skill → 配置Garmin中国区MCP → 用户安全认证 → 读取数据。**

<!-- INSTALL:GARMIN:START -->
```text
请从 https://github.com/isbenny/runwise-ai-coach/tree/v0.1.1 读取 README.md、SKILL.md 及 references/garmin-cn.md，为我安装 RunWise AI Coach（Skill 名称 runwise-coach），我使用佳明中国大陆账号。
先检查你是否能安装 Agent Skill、执行本地命令、加载本地 stdio MCP，以及是否有私有持久存储；展示将新增的文件、依赖、MCP配置及训练摘要的数据去向，等我确认后才安装。只用 v0.1.1 固定版本；可从 https://github.com/isbenny/runwise-ai-coach/releases/tag/v0.1.1 下载 Skill ZIP 和校验文件，校验 SHA256 后安装到我指定的工作区，不覆盖已有配置，不修改全局设置。
优先复用我已有的只读 Garmin MCP；没有时，按适配说明把 Taxuspt/garmin_mcp 固定 commit a2ca5fcac34524b83814fe2fcf3d479f8a75983f 装到独立环境，仅启用 get_activities、get_activities_by_date、get_activity、get_activity_splits。该上游的账号读取尚待本人实际验证，不能借用旧适配器结果声称已经连接。
认证只由我在安全本机交互入口完成，不向聊天、网页或公开配置索取账号、密码、验证码或 Token；无安全入口就停止并说明。真实发现工具并授权后，先展示读取范围和预算，再读取我的活动；缺失数据标明缺口。根据我确认的目标、训练日和恢复状态提出课表草案，确认后保存到我的私有存储；反馈调课先展示差异，独立新会话重新读取。不能保存时明确说未保存，不用开发者数据、不部署云端、不写回手表。
```
<!-- INSTALL:GARMIN:END -->

## 高驰用户：复制给你的 AI 助手

**复制安装指令 → AI助手安装稳跑Skill → 配置高驰官方MCP → 用户通过官方OAuth授权 → 读取数据。**

<!-- INSTALL:COROS:START -->
```text
请从 https://github.com/isbenny/runwise-ai-coach/tree/v0.1.1 读取 README.md、SKILL.md 及 references/coros-cn.md，为我安装 RunWise AI Coach（Skill 名称 runwise-coach），我使用高驰中国区账号。
先检查你是否支持 Agent Skill、远程 HTTPS MCP、OAuth/PKCE授权以及私有持久存储；展示将新增的文件、连接、权限及训练摘要的数据去向，等我确认后才安装。只用 v0.1.1 固定版本；可从 https://github.com/isbenny/runwise-ai-coach/releases/tag/v0.1.1 下载 Skill ZIP 和校验文件，校验 SHA256 后安装到我指定的工作区，不覆盖已有配置，不修改全局设置。
高驰只连接官方 https://mcpcn.coros.com/mcp，由我在高驰官方页面完成 OAuth。不要索取密码或 Token，不安装 Garmin 库，不复用其他账号授权。先发现真实工具及输入格式，只启用可确认的训练读取能力，不猜工具名；WorkBuddy 5.8.3 已有官方授权与读数验证；你仍须为我本人账号实际发现工具并读取，不借用他人的结果。
真实工具可用后展示读取范围和预算，再读取我的训练，明确数据不足；根据我确认的目标、训练日和恢复状态提出课表草案。确认后保存到我的私有存储，反馈调课先展示差异，独立新会话重读。若缺 Skill、OAuth、计算或存储能力，准确说明限制，不把普通手机聊天或本地 stdio 说成已经支持，不另建云端后台，不写回手表。
```
<!-- INSTALL:COROS:END -->

这两段指令是让具备对应能力的AI协助安装，**不是声称任意聊天窗口都能GitHub URL一键导入**。没有工具安装能力时，AI应停止并说明。安装器只装Skill，不自动配置MCP、登录或读取数据。

## 下载与手动安装

正式发布后使用本仓库的 [v0.1.1 Release](https://github.com/isbenny/runwise-ai-coach/releases/tag/v0.1.1)，下载 `runwise-coach-skill-v0.1.1.zip` 和同名 `.sha256`。核对ZIP SHA256后解压；包内 `SHA256SUMS` 校验各文件。

具备命令能力的桌面宿主，可从仓库固定tag获取源码：

```sh
git clone --branch v0.1.1 --single-branch https://github.com/isbenny/runwise-ai-coach.git
cd runwise-ai-coach
python3 scripts/preflight.py --workspace /你的现有AI工作区
python3 scripts/install.py --workspace /你的现有AI工作区
# 本人核对预览并确认后：
python3 scripts/install.py --workspace /你的现有AI工作区 --apply
```

上面工作区路径须换成本人的实际目录，不能原样照抄。Skill固定安装到该工作区`.agents/skills/runwise-coach`；仓库名与Skill安装名不同。重复安装同一内容返回unchanged，已有改动则保留并停止，不覆盖。其他宿主按其官方Agent Skills方式加载本目录，未实测宿主不标已支持。

## 两种连接必须分别处理

| 手表 | 接入方式 | 当前验证边界 |
|---|---|---|
| Garmin中国区 | 已有只读MCP优先；可选固定Taxuspt本地stdio | 原Garmin CN适配器真实读取已验证。Taxuspt已隔离安装、空凭据发现四项只读工具；**该上游本人账号读数未验收**，不是Garmin官方合作OAuth |
| COROS中国区 | [官方HTTPS MCP](https://mcpcn.coros.com/mcp) + 官方OAuth | WorkBuddy 5.8.3 已完成本人官方OAuth、工具发现及单条活动读取；其他宿主与新用户账号仍须各自验证 |

详细步骤：[Garmin安装与安全认证](references/garmin-cn.md) · [COROS官方OAuth](references/coros-cn.md)。不需要安装旧开发工程或继承开发者数据库。Token仅留在本人私有缓存/宿主OAuth存储，密码、验证码不能发送到AI对话或公开Issue。

## 哪些AI客户端已验证

| 宿主能力 | 状态 |
|---|---|
| macOS桌面Codex，支持项目Skill、命令和stdio MCP | 已实际安装候选Skill、重复安装、真实MCP读数、隔离计划/模拟反馈保存与独立新会话续读；117项既有回归通过 |
| WorkBuddy 5.8.3（macOS桌面） | 官方Skill导入/加载、既有Garmin只读MCP读数、COROS官方OAuth/活动读取、新任务重新读取及未保存草案已实测；不代表Taxuspt新账号或正式课表保存已验收 |
| 其他桌面Agent Skills + MCP宿主 | 安装规范可用；未逐客户端实测，不承诺所有版本支持 |
| 手机AI助手 | **Skill安装完整流程未验收**。需同时支持Skill、远程MCP、官方授权及存储；本地stdio不能直接在手机运行 |
| GitHub URL一键导入 | **没有通用一键导入承诺**；由宿主按真实能力安装 |

历史手机合成工具调用成功不代表手机已能安装本Skill，也不代表Garmin公开自动同步已上线。

## 安装之后怎么用

- “更新训练数据，分析最近一次跑步和近期趋势。”先确认日期范围、请求预算和AI数据去向，再主动读取；无后台同步或推送。
- “我的比赛目标是……，每周可跑……，请生成未来7天课表。”先补足目标、训练日与恢复状态，生成7天详细草案及4周条件框架；未知比赛日期、阈值、处方配速不填造。
- “这次RPE……，疲劳……，局部症状……，请调整后续课表。”展示未来3–7天原/建议安排、触发原因与证据；你确认后才生效，支持拒绝及回滚。
- “读取我的最新档案和正式课表。”新会话读同一私有存储，不能只依赖旧聊天。无持久存储时只能导出草案，不能声称已保存。

AI负责解释，准确数值优先交给现有Core/MCP结果。可选离线计算只需Python≥3.10和`requirements-calculations.txt`，在本人确认的隔离环境安装。入口：`python3 scripts/coach.py contracts`；格式见[计算契约](references/calculations.md)。不重写训练算法，不用平均配速编造分段，不凭缺失RPE/有效阈值断言训练过量或鼓励加速。

## 档案、计划和隐私

[空档案](assets/profile.json)没有个人参数，[空计划封装](assets/plan-template.json)不是训练处方。正式Core档案输入需遵循`coach.py contracts`返回结构；空计划封装不能直接传给adjust。保存规范见[宿主持久化](references/persistence.md)。确认后把个人文件存到自己的私有目录并排除Git，保留版本与来源，新会话核验current指针。

源码及Release不应出现Token、.env、SQLite、活动详情、GPS、真实计划、反馈、日志或本地环境。请勿把这些提交到Issue/PR；如报告问题，只提供去敏错误类型。不会修改Garmin/COROS活动、日历或设备，不额外调用模型API。

## 版本与第三方

[CHANGELOG](CHANGELOG.md) · [第三方声明](THIRD_PARTY_NOTICES.md) · [依赖许可证清单](references/dependency-licenses.json)。第三方MCP不随包分发，按各自条款授权。训练计算与认证运行文件沿用已验收版本；v0.1.1只增加WorkBuddy安装适配说明、私有配置合并预览及版本校验。

[Agent Skills规范](https://agentskills.io/specification)。参考项目只借鉴轻量交付形式，没有复制其未经本工程验证的训练参数。
