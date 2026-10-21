# 既有计算代码的轻量入口

包内scripts/_core保留原CORE-01/02必要模块的原字节；core-provenance.json逐文件记录SHA256。`coach.py`只做严格SI契约→**内存临时表**→原计算函数，不需要历史数据库，不创建数据库文件、不联网、不读取凭据、不保存正式计划。没有新的训练引擎。

先运行 `python3 scripts/coach.py contracts` 获取实际输入、档案及反馈schema；需要jsonschema时只在宿主隔离环境安装requirements-calculations.txt，经本人确认。普通Skill安装本身不安装Python或依赖。

输入`runwise-mcp-input/1`含：provider/region（garmin/garmin.cn或coros/coros.cn）、as_of北京时间日期、source_tool、coverage(start/end/complete)、activities。活动记录包含source_id、kind、带时区started_at、SI字段distance_m/timer_s/moving_s/elapsed_s/avg_hr_bpm/max_hr_bpm/avg_power_w、原圈laps及laps_complete。无圈为[]、false；圈提供lap_source_tool。其他字段禁止进入计算输入，包括凭据/GPS。

从所选MCP**逐字段复制**真实值；缺少指标用null，不补0。单位不明就停止转换并报告，不能猜。无时区本地时间只在适配说明明确允许时附Asia/Shanghai偏移，timezone_assumption写明假设。原始文本保留在宿主私有来源记录中，不进入源码包。

同一提供方ID相同内容会去重，矛盾内容报错；同日不同ID保留。报告沿用原逐指标质量隔离，可靠距离不会因缺心率自动作废。圈只凭明确真实圈接口和完整性证据标完整，不从平均值生成。

```sh
python3 scripts/coach.py report --input /私有目录/snapshot.json --output /私有目录/report-new.json
python3 scripts/coach.py plan --input /私有目录/snapshot.json --profile /私有目录/profile.json --start YYYY-MM-DD --output /私有目录/draft-new.json
python3 scripts/coach.py adjust --input /私有目录/snapshot.json --profile /私有目录/profile.json --plan /私有目录/plan-data.json --feedback /私有目录/feedback.json --activity 实际来源ID --days 7 --output /私有目录/proposal-new.json
```

路径是说明，AI必须使用本人实际私有位置，不照抄占位文件名。输出不覆盖已有文件；`persisted=false`表示没有写正式档案或课表。带--output只是保存一个计算结果，不代表用户已批准计划。正式保存遵守persistence.md。

生成正常马拉松计划需要完整42天覆盖、目标/日期或范围、已确认训练日和近期恢复状态；缺失时返回needs_information/needs_confirmation。不能把只读最近5条当历史完整。四周框架始终是条件性建议。

调课复用Core的主观反馈及新长距离证据规则。外部快照本身不能证明某次训练前已有正式目标，所以默认**不判定客观超量或结构达标**；已有Core MCP的正式计划对照仍以其报告为准。反馈观察时间、活动ID必须真实一致；不允许模型伪造模拟输入为本人反馈。

日期/星期/自然周由返回calendar提供。未知阈值不生成具体配速；没有真实圈时不会生成假分段。异常字段与不全覆盖需同报告一起展示。
