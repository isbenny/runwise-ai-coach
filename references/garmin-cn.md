# Garmin中国区：独立适配

## 选择与证据

优先检查用户**已经安装**的Garmin MCP；本工程的只读MCP已有真实中国区与圈数据验证，可继续复用。普通新用户不需要安装原历史数据库。

第三方候选：[Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp)，本轮审查固定commit `a2ca5fcac34524b83814fe2fcf3d479f8a75983f`。其源码支持 `GARMIN_IS_CN=true`、本机预认证、stdio和工具白名单。它还包含活动修改、课表发布等写工具，**不可默认全部开启**。这不是Garmin官方OAuth合作授权。该commit固定`garminconnect==0.3.2`，与原工程0.3.19不同，必须隔离安装，不能替换原工程依赖。

## 安装前预览

由AI检查工具安装能力，展示：安装位置、固定commit、独立环境、凭据缓存目录、MCP配置差异、四项只读工具、网络和AI数据去向；确认后才执行。不要用管理员权限、全局配置覆盖、默认缓存搜索或把密码写到env。

具备uv的桌面可在全新受限目录安装：

```sh
uv venv --python 3.12 .garmin-mcp-venv
uv pip install --python .garmin-mcp-venv/bin/python 'git+https://github.com/Taxuspt/garmin_mcp@a2ca5fcac34524b83814fe2fcf3d479f8a75983f'
```

没有uv/Python时，先展示宿主支持的包安装方式，取得确认后按官方方式安装；没有命令能力不能谎称已完成。不要把此前32MB本机运行包变成所有用户的前提。

## 本人本机认证

推荐用包内安全交互薄包装调用上游认证，不复制登录逻辑：

```sh
.garmin-mcp-venv/bin/python scripts/garmin_auth.py --state-dir /本人指定的私有目录
```

脚本只允许真实本机TTY，账号/密码/MFA均隐藏输入，抑制上游包含账号的状态输出；只转达成功或错误类型，不打印Token。它使用独立缓存目录和现成上游认证。不要把此命令放入MCP启动参数；需要本人打开终端运行。MCP无TTY时停止并给此入口，不能等待密码。

## MCP配置差异

下列是**结构说明**，由安装器/AI用本机实际绝对路径生成预览，不作为可直接复制的公开假配置：

- command：独立环境的绝对 `garmin-mcp` 可执行路径。
- args：空。
- env：`GARMIN_IS_CN=true`，`GARMIN_MCP_TRANSPORT=stdio`，`GARMINTOKENS`为本人专属缓存路径；`GARMINTOKENS_BASE64`为同一私有目录的缓存文件路径，绝不是Token字符串。
- `GARMIN_ENABLED_TOOLS=get_activities,get_activities_by_date,get_activity,get_activity_splits`。
- 不含GARMIN_EMAIL、GARMIN_PASSWORD或其他明文凭据；不启HTTP公网服务。

仅修改用户确认的本产品条目，先备份，保留其他MCP。优先项目级；WorkBuddy使用已核实的官方设置入口，用户级访问范围须另外说明并由本人确认，见[WorkBuddy步骤](workbuddy-desktop.md)。实际tools/list须与这四项一致；工具注解不能代替真正的白名单。

授权后，先读取近期一页、最近活动详情和必要真实圈；之后按明确范围分页。`get_activities_by_date`的has_more为true必须继续或标部分完成。上游date查询页字段为distance_meters/duration_seconds，部分列表不含移动和经过时长，不能补0；详情才有moving_duration_seconds/elapsed_duration_seconds。`get_activity_splits`才是圈接口，保留每圈distance_meters和intensity_type，不按1km虚构。

列表start_time是本地无时区文本，明确按中国区Asia/Shanghai处理并保留假设；详情start_time_gmt是UTC。仅读取摘要、必要圈，不取FIT/GPS。活动标题不作为训练结构证据。

未对Taxuspt完成本人账号实测时，只能标“源码核查/无凭据协议验证”，不能借用旧适配器的成功声称上游已实测。认证失效停下，由本人安全重新认证，不换区、不反复请求。个人渠道能用也不等于获准公开代理他人的账号。
