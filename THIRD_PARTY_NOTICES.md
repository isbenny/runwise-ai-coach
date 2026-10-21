# 第三方组件与许可范围

本仓库不打包第三方MCP、Python解释器或依赖包；只保留本项目必要的计算源文件与认证薄入口。此处的MIT等许可均不替代本项目自身的LICENSE状态。

| 组件 | 版本/来源 | 本包使用方式与许可 |
|---|---|---|
| Taxuspt/garmin_mcp | commit a2ca5fcac34524b83814fe2fcf3d479f8a75983f | 独立安装和导入上游认证；未复制其MCP实现。MIT，Alexandre Domingues，2025；原许可见 licenses/Taxuspt-garmin_mcp-MIT.txt |
| jsonschema | 4.26.0 | 可选计算依赖，不打包其实现。当前发行包元数据标MIT；原许可见 licenses/jsonschema-MIT.txt |
| attrs / jsonschema-specifications / referencing / rpds-py / typing-extensions | 已验收环境版本见 references/dependency-licenses.json | jsonschema所需依赖，未随包分发；按各自安装包的许可和声明使用 |
| COROS中国区官方MCP | https://mcpcn.coros.com/mcp | 官方远程OAuth服务；没有复制或分发其服务代码。以官方授权页及服务条款为准，本项目不代为接受 |
| xiaolouJB/ai-running-coach | https://github.com/xiaolouJB/ai-running-coach | 只参考轻量交付形式，未复制代码、提示词或训练参数，未将其许可套用到本项目 |

Coach Core必要模块来自原本地RunWise工程，逐文件来源SHA256见references/core-provenance.json。源码按原字节复用，没有复制第三方训练算法。若安装第三方MCP，其更完整的依赖链由该上游项目维护，本仓库没有把可选上游依赖误列为自己已经分发的组件。

固定来源：
- https://github.com/Taxuspt/garmin_mcp/tree/a2ca5fcac34524b83814fe2fcf3d479f8a75983f
- https://github.com/python-jsonschema/jsonschema
- https://agentskills.io/specification

许可证检查与隐私检查是不同的门槛；没有因为依赖可开源就擅自为本项目授予开源许可。
