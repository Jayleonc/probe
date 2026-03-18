Probe Roadmap

1. 项目定位

1.1 项目名称

Probe

1.2 一句话定义

Probe 是一个部署在运维机上的只读排障查询 MCP 服务，为宿主机上的 Agent 提供受限、结构化、安全的日志查询能力。

1.3 第一阶段目标

快速实现一个最小可用版本，使 Agent 能够：
	1.	按服务查询日志
	2.	按关键词查询日志
	3.	按 request_id / trace_id 查询日志
	4.	获取某条命中的上下文日志
	5.	在严格只读和受限权限下返回结构化结果

1.4 非目标

第一阶段不做以下事情：
	1.	不提供任意 Shell 执行能力
	2.	不允许修改文件、删除文件、写入文件
	3.	不允许访问任意目录
	4.	不做复杂代码分析
	5.	不做自动修复
	6.	不做全量可观测平台
	7.	不接入生产写权限或远程控制能力

⸻

2. 核心设计原则

2.1 只读优先

Probe 只提供读取能力，不提供任何写入、修改、执行变更类能力。

2.2 暴露意图，不暴露命令

对外提供的是“查询日志”的工具，不是“执行命令”的能力。

错误方向示例：
	•	run_command(“grep xxx /path/to/log”)

正确方向示例：
	•	search_logs(service, keyword, start_time, end_time, limit)
	•	search_by_request_id(service, request_id, limit)
	•	tail_errors(service, lines)

2.3 安全边界前置

所有功能默认在白名单、目录限制、返回大小限制、时间范围限制下运行。

2.4 结果结构化

返回结果必须适合 Agent 消费，避免直接返回不可控的大段终端输出。

2.5 先跑通场景，再演进架构

第一版先解决真实排障问题，优先闭环，再考虑索引、检索优化、多服务复制。

⸻

3. 使用场景

3.1 场景一：按错误关键词排查

用户输入：
“帮我看看 gateway 今天下午为什么大量 timeout。”

Agent 调用 Probe：
	1.	查询 gateway 在指定时间范围内的 ERR 日志
	2.	搜索 timeout 关键词
	3.	抽取代表性上下文
	4.	返回给 Agent 进行初步归因

3.2 场景二：按 request_id 定位一条请求

用户输入：
“帮我查一下 req_id=abc123 这一条请求发生了什么。”

Agent 调用 Probe：
	1.	search_by_request_id
	2.	获取同 request_id 的多条日志
	3.	按时间排序输出
	4.	让 Agent 还原请求轨迹

3.3 场景三：快速查看某服务最近错误

用户输入：
“最近 scheduler 是不是一直在报错？”

Agent 调用 Probe：
	1.	tail_errors(service=scheduler)
	2.	提取最近错误
	3.	汇总错误类型

⸻

4. MVP 范围

4.1 第一版必须实现的能力

Tool 1: search_logs
按服务、关键词、时间范围搜索日志。

Tool 2: search_by_request_id
按 request_id / trace_id 搜索关联日志。

Tool 3: tail_errors
查看某服务最近 N 条错误日志。

Tool 4: context_around_match
查看某条日志命中前后的上下文。

4.2 第一版可选能力

Tool 5: list_services
列出当前允许查询的服务清单。

Tool 6: health_check
返回 Probe 服务自身健康状态和版本信息。

4.3 第一版暂不实现
	1.	多机聚合查询
	2.	指标查询
	3.	配置文件查询
	4.	SQL 查询
	5.	代码检索
	6.	向量检索
	7.	用户权限系统
	8.	Web UI

⸻

5. MCP Tool 设计

5.1 tool: list_services

目的
让 Agent 知道当前可查询的服务白名单。

输入
无

输出示例

{
  "services": ["gateway", "scheduler", "im", "order"]
}


⸻

5.2 tool: search_logs

目的
按服务、关键词、时间范围搜索日志。

输入

{
  "service": "gateway",
  "keyword": "timeout",
  "start_time": "2026-03-18T15:00:00",
  "end_time": "2026-03-18T16:00:00",
  "level": "ERR",
  "limit": 20
}

输入约束
	1.	service 必须在白名单内
	2.	keyword 不能为空
	3.	start_time / end_time 必须合法
	4.	时间范围不能超过配置上限，例如 24 小时
	5.	limit 不能超过最大值，例如 50

输出示例

{
  "service": "gateway",
  "query": {
    "keyword": "timeout",
    "start_time": "2026-03-18T15:00:00",
    "end_time": "2026-03-18T16:00:00",
    "level": "ERR",
    "limit": 20
  },
  "summary": {
    "total_matches": 18,
    "returned_matches": 5,
    "truncated": true
  },
  "items": [
    {
      "id": "match_001",
      "timestamp": "2026-03-18T15:03:12",
      "level": "ERR",
      "file": "gateway.log",
      "line_number": 18231,
      "text": "dial tcp 10.0.0.12:9001: i/o timeout"
    }
  ],
  "next_actions": ["context_around_match", "search_by_request_id"]
}


⸻

5.3 tool: search_by_request_id

目的
按 request_id 或 trace_id 搜索同一请求链路相关日志。

输入

{
  "service": "gateway",
  "request_id": "abc123",
  "limit": 50
}

输出示例

{
  "service": "gateway",
  "request_id": "abc123",
  "summary": {
    "total_matches": 12,
    "returned_matches": 12
  },
  "items": [
    {
      "timestamp": "2026-03-18T15:03:10",
      "level": "INF",
      "file": "gateway.log",
      "line_number": 18220,
      "text": "start request req_id=abc123 path=/api/pay"
    },
    {
      "timestamp": "2026-03-18T15:03:12",
      "level": "ERR",
      "file": "gateway.log",
      "line_number": 18231,
      "text": "downstream payment timeout req_id=abc123"
    }
  ]
}


⸻

5.4 tool: tail_errors

目的
读取某服务最近 N 条错误日志。

输入

{
  "service": "scheduler",
  "lines": 30
}

输出示例

{
  "service": "scheduler",
  "summary": {
    "returned_lines": 30
  },
  "items": [
    {
      "timestamp": "2026-03-18T16:11:01",
      "level": "ERR",
      "file": "scheduler.log",
      "line_number": 90121,
      "text": "job execute failed: connection refused"
    }
  ]
}


⸻

5.5 tool: context_around_match

目的
查看某条日志命中的上下文，用于还原前因后果。

输入

{
  "service": "gateway",
  "file": "gateway.log",
  "line_number": 18231,
  "before": 10,
  "after": 10
}

输出示例

{
  "service": "gateway",
  "file": "gateway.log",
  "line_number": 18231,
  "context": {
    "before": [
      "2026-03-18T15:03:10 INF start request req_id=abc123",
      "2026-03-18T15:03:11 INF calling downstream payment"
    ],
    "match": "2026-03-18T15:03:12 ERR downstream payment timeout req_id=abc123",
    "after": [
      "2026-03-18T15:03:12 INF retry count=1",
      "2026-03-18T15:03:13 ERR request failed cost=3001ms"
    ]
  }
}


⸻

6. 安全设计

6.1 目录白名单

只允许访问配置中的日志目录，例如：
	•	/data/logs
	•	/var/log/app

禁止访问白名单之外的任何目录。

6.2 服务白名单

每个 service 预先映射到固定日志路径，不允许用户自行拼路径。

示例：

services:
  gateway:
    log_paths:
      - /data/logs/gateway/gateway.log
  scheduler:
    log_paths:
      - /data/logs/scheduler/scheduler.log

6.3 禁止任意命令执行
	1.	不提供 run_command 之类的能力
	2.	不允许传 shell 片段
	3.	如需复用现有脚本，只能通过固定参数模板调用
	4.	严禁 shell=True

6.4 返回大小限制
	1.	单次最大返回条数限制，例如 50
	2.	单次最大返回文本大小限制，例如 64KB
	3.	超过时截断并标记 truncated=true

6.5 时间范围限制
	1.	默认最近 1 小时
	2.	最大允许查询 24 小时或 7 天，由配置控制

6.6 敏感信息脱敏

对返回文本中的以下内容做基础脱敏：
	1.	token
	2.	cookie
	3.	手机号
	4.	身份证号
	5.	access_key / secret_key

6.7 审计日志

记录：
	1.	调用时间
	2.	调用 tool
	3.	查询参数摘要
	4.	返回数量
	5.	是否截断
	6.	是否异常

⸻

7. 技术方案

7.1 技术选型建议

语言
Python 3.11+

原因
	1.	迭代快
	2.	适合做 MCP 工具封装
	3.	适合做文件读取、脚本包装、参数校验
	4.	第一版瓶颈不在极致性能

框架建议
	•	MCP Python SDK
	•	Pydantic 用于入参与出参模型
	•	asyncio 用于并发查询控制
	•	subprocess 用于安全调用现有脚本
	•	pathlib 用于路径处理
	•	PyYAML 用于配置文件

7.2 底层实现路线

路线 A：优先复用现有稳定脚本
适合场景：
团队已有成熟日志查询脚本。

优点：
	1.	快速复用经验
	2.	与现有运维习惯一致
	3.	快速验证价值

注意：
必须通过固定参数方式调用，不能暴露任意脚本执行能力。

路线 B：Python 直接读取日志文件
适合场景：
脚本较乱、不可控、格式不稳定。

优点：
	1.	可控性更强
	2.	结果结构化更容易
	3.	安全边界更清晰

建议：
MVP 优先选最能快速落地的一条，不纠结“架构纯洁性”。

⸻

8. 项目目录结构建议

probe/
├── README.md
├── ROADMAP.md
├── pyproject.toml
├── probe/
│   ├── __init__.py
│   ├── main.py                 # MCP server 启动入口
│   ├── config.py               # 配置加载
│   ├── models.py               # Pydantic 模型
│   ├── server.py               # MCP tool 注册
│   ├── settings/
│   │   └── config.example.yaml
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── list_services.py
│   │   ├── search_logs.py
│   │   ├── search_by_request_id.py
│   │   ├── tail_errors.py
│   │   └── context_around_match.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── log_service.py      # 查询编排、校验、截断、脱敏
│   │   ├── audit_service.py    # 审计日志
│   │   └── redact_service.py   # 敏感信息脱敏
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── script_adapter.py   # 包装现有脚本
│   │   └── file_adapter.py     # 直接读文件
│   └── utils/
│       ├── __init__.py
│       ├── time_utils.py
│       ├── path_utils.py
│       └── text_utils.py
└── tests/
    ├── test_search_logs.py
    ├── test_search_by_request_id.py
    ├── test_tail_errors.py
    └── test_context_around_match.py


⸻

9. 核心模块职责

9.1 server.py

负责：
	1.	初始化 MCP server
	2.	注册所有 tools
	3.	把 tool 请求转发给 services 层

9.2 models.py

负责：
	1.	定义输入输出 schema
	2.	参数合法性校验
	3.	统一错误消息结构

9.3 log_service.py

负责：
	1.	service 白名单校验
	2.	时间范围校验
	3.	limit 截断
	4.	调用 adapter
	5.	统一结果结构化
	6.	统一脱敏
	7.	记录审计

9.4 adapters

负责：
	1.	和底层脚本或文件系统交互
	2.	返回原始日志数据
	3.	不承担复杂业务规则

⸻

10. 配置文件设计

10.1 config.example.yaml

server:
  name: probe
  environment: dev
  audit_log_path: /var/log/probe_audit.log

limits:
  max_lines: 50
  max_bytes: 65536
  max_time_range_hours: 24
  command_timeout_seconds: 10

security:
  redact_enabled: true
  allow_script_adapter: true

services:
  gateway:
    log_paths:
      - /data/logs/gateway/gateway.log
    request_id_patterns:
      - "req_id="
      - "request_id="
  scheduler:
    log_paths:
      - /data/logs/scheduler/scheduler.log
    request_id_patterns:
      - "req_id="

10.2 环境命名建议

服务实例名规则：
{biz}-probe-{env}

示例：
	•	hailiang-probe-dev
	•	hailiang-probe-test
	•	hailiang-probe-prod
	•	quanliang-probe-dev

⸻

11. 开发顺序建议

Phase 1: 跑通最小骨架

目标：
让 MCP server 可以启动，并暴露一个最简单 tool。

任务：
	1.	初始化 Python 项目
	2.	接入 MCP Python SDK
	3.	实现 health_check 或 list_services
	4.	本地成功调用一次 tool

验收标准：
	•	Agent 能成功连接 Probe
	•	能返回可解析 JSON

Phase 2: 实现基础日志查询

目标：
实现 search_logs。

任务：
	1.	定义 SearchLogsRequest / Response
	2.	实现 service 白名单校验
	3.	实现底层日志搜索
	4.	加上 limit 截断
	5.	加上错误处理

验收标准：
	•	能按 service + keyword + time_range 查询日志
	•	超限会被截断
	•	非法 service 被拒绝

Phase 3: 实现 request_id 查询

目标：
实现 search_by_request_id。

任务：
	1.	定义 request_id 查询模型
	2.	支持按 request_id 聚合命中
	3.	按时间排序返回

验收标准：
	•	能通过 request_id 拉出一条请求的多条日志

Phase 4: 实现上下文查询

目标：
实现 context_around_match。

任务：
	1.	支持 file + line_number 定位
	2.	返回前后若干行
	3.	做边界保护

验收标准：
	•	命中日志可回看上下文

Phase 5: 安全加固

目标：
把 MVP 从“能跑”提升到“能安全试用”。

任务：
	1.	加审计日志
	2.	加敏感信息脱敏
	3.	加超时控制
	4.	加返回大小限制
	5.	补齐异常处理

验收标准：
	•	所有 tool 都经过统一校验与审计
	•	不会暴露敏感内容或无限返回

⸻

12. AI 实现提示要求

下面这部分可以直接给 AI 编码助手使用。

12.1 实现目标

请基于本 ROADMAP 实现一个 Python 版 Probe MVP。要求：
	1.	使用 Python 3.11+
	2.	使用 MCP Python SDK
	3.	使用 Pydantic 定义请求与响应模型
	4.	默认只实现 list_services、search_logs、search_by_request_id、tail_errors、context_around_match
	5.	严格只读
	6.	严禁提供任意命令执行能力
	7.	所有结果统一输出 JSON 结构
	8.	代码按 ROADMAP 的目录结构组织
	9.	优先保证可运行、可测试、可扩展
	10.	先做 MVP，不做过度设计

12.2 实现约束
	1.	不要使用 shell=True
	2.	不要暴露 run_command 接口
	3.	所有 service 必须从配置读取白名单
	4.	所有文件访问必须经过路径校验
	5.	所有 tool 都要有参数校验和错误处理
	6.	所有返回都要支持 truncation 标记
	7.	所有文本返回都要经过脱敏处理开关

12.3 交付要求

请输出：
	1.	完整项目目录结构
	2.	可运行代码
	3.	示例配置文件
	4.	至少 4 个核心测试用例
	5.	README 的启动说明
	6.	每个模块的职责注释

⸻

13. 验收标准

13.1 功能验收
	1.	Agent 能调用 Probe 的 4 个核心查询 tool
	2.	能查询指定服务日志
	3.	能按 request_id 查询关联日志
	4.	能查看最近错误
	5.	能查看上下文

13.2 安全验收
	1.	不支持任意命令执行
	2.	不支持读取白名单外文件
	3.	不支持无限制返回数据
	4.	不支持写入或修改操作
	5.	审计日志正常记录

13.3 工程验收
	1.	目录结构清晰
	2.	模块职责清晰
	3.	配置驱动
	4.	有基础测试
	5.	错误信息可读

⸻

14. 后续演进方向

14.1 第二阶段
	1.	多服务并行查询
	2.	错误聚类汇总
	3.	更强的时间范围过滤
	4.	日志格式解析器
	5.	更智能的 request_id 自动识别

14.2 第三阶段
	1.	增加指标查询能力
	2.	增加状态查询能力
	3.	增加配置只读查询能力
	4.	统一成通用诊断查询层

14.3 长期方向

Probe 可以从“只读日志查询 MCP”演进成“只读诊断 MCP 基础设施”，服务于多个业务系统和环境，通过前缀和配置复用到不同微服务体系中。

⸻

15. 最终结论

Probe 第一阶段不追求大而全。

只要做到下面这件事，这个项目就成立：

程序员只说一句“帮我看看某个服务为什么报错”，Agent 就能调用 Probe，在受限、只读、安全的前提下，把有价值的日志证据拿回来。

这就是第一阶段最核心的成功标准。
