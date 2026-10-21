# COROS中国区：官方远程MCP

唯一指定端点：**https://mcpcn.coros.com/mcp**。这是高驰官方远程服务，不是本机stdio；不安装Garmin库，不索取高驰密码，不把Garmin Token或缓存复制过去。

## 本轮已核查

2026-10-21，未带凭据的真实initialize请求返回401；WWW-Authenticate指向官方受保护资源元数据：

- https://mcpcn.coros.com/.well-known/oauth-protected-resource/mcp
- resource为上述/mcp，authorization_server为https://mcpcn.coros.com
- 支持openid、mcp.tools、offline_access及header Bearer。

授权服务器元数据真实返回authorization_code、refresh_token、S256 PKCE及客户端注册入口。这只证明OAuth入口存在，不等于本人授权、数据读取、手机支持已验收。scope名称没有直接证明业务只读，必须进一步核对授权页与工具能力。

## 用户路径

1. 检查宿主是否支持远程HTTPS MCP、OAuth回调/PKCE（或其受支持的设备授权）、Skill及持久存储。只有普通网页聊天不能默认支持。
2. 展示新增连接及所请求scope/数据用途，取得确认；在宿主添加上面的URL，不在配置放Token。
3. 由本人在**高驰官方授权页**登录并授权；核对域名、账号与权限。不要替用户输入密码，不自行构造授权code/client_secret，不把其他MCP的登录流程套上来。
4. OAuth完成后实际发现tools/list及各schema；本轮没有授权后的工具目录，因此不预填或猜测高驰工具名。只启活动摘要/必要圈的读取工具，拒绝日历/训练/活动修改。
5. 按用户请求读取一条真实活动并核对单位、日期、活动ID、圈类型；再分页读取所需窗口。未核实单位不得套用Garmin CSV规则。无圈则报告未取得。
6. 宿主能执行计算时，按calculations.md映射到SI契约；只复制已核验字段，不猜单位。不能运行计算则使用MCP确定性结果并说明局限。

Token由宿主OAuth存储管理。过期时由宿主正常刷新；撤销/refresh失败停止读取，提示本人在同一官方入口重新授权。不能反复登录或复用其他用户授权。

手机只有在上述完整流程真实完成后才标支持。本轮没有高驰账号授权证据，不开展新平台试错或建设自有后端来替代。
