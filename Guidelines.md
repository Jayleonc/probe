这份指南将作为即将负责执行 Probe（日志排障查询 MCP 服务） 项目落地的 AIAgent 的核心行为准则。
这份指南结合了 ROADMAP.md 的业务约束，以及官方 Model Context Protocol (MCP) 规范和 Python SDK 的最佳实践。

--------------------------------------------------------------------------------
AIAgent 落地执行指南：Probe (日志排障 MCP 服务)
To AIAgent: 你的任务是根据给定的 ROADMAP.md，使用 Python 开发一个名为 Probe 的 MCP Server。这个服务将作为连接大模型与主机本地日志的只读桥梁（类似于封装 glog.sh 等排障脚本）。在编码和架构设计时，请严格遵循以下准则：
一、 MCP 协议开发“避坑”指南 (致命红线)
在编写 Python MCP Server 时，有几个协议层的严格规范极易导致服务崩溃或无法通信，必须死死守住：
绝对禁止输出到 Standard Output (stdout)
：
由于 Probe 将使用 stdio 传输模式，Client 会通过标准输入输出与 Server 进行 JSON-RPC 通信。
任何 print() 语句、或使用标准输出的第三方日志库，都会破坏 JSON-RPC 消息格式并导致 Server 崩溃
。
正确做法：如果需要打印调试日志，必须将其写入 stderr（标准错误输出）或写入到指定的文件中（如 Roadmap 中提到的 audit_log_path）
。
区分“工具执行错误”与“协议错误”
：
当工具执行失败（例如：输入的 service 不在白名单中、时间格式错误、日志文件不存在等业务逻辑错误）时，不要直接抛出 Python Exception 导致请求中断。
正确做法：应该返回一个 CallToolResult，并在其中设置 isError=True，将具体的错误提示放在 content 中
。这样客户端的 LLM 就能“看到”错误原因，并有机会自我纠正参数重新查询
。
二、 架构与技术栈实现建议
根据 Roadmap 要求，你需要使用 Python 3.11+ 和 MCP Python SDK 进行开发。
首选 FastMCP 框架
：
建议使用 mcp.server.fastmcp.FastMCP。它利用 Python 的 Type Hints (类型提示) 和 Docstrings (文档字符串) 自动生成工具定义和 JSON Schema，能极大减少样板代码
。
你可以通过简单的 @app.tool() 装饰器将 search_logs、search_by_request_id 等函数直接暴露给 Client
。
充分利用 Pydantic 进行输入校验：
Roadmap 要求严格的参数限制。利用 Pydantic 定义 SearchLogsRequest 等模型，能自动拦截非法的 limit 大小、错误的时间格式等，确保 MCP Server 接收到的参数绝对安全。
三、 安全与权限边界 (最高优先级)
Probe 的核心定位是受限、只读、安全。你必须在代码中筑起三道安全防火墙：
禁止任意代码/命令执行 (RCE 防护)：
在实现 adapters 层（无论是包装类似 glog.sh 还是用 grep）时，如果使用 subprocess，绝对禁止使用 shell=True。
所有传递给命令的参数（如 keyword 或 request_id）必须作为独立的 List 元素传递，并在传入前做严格的正则表达式校验（防止注入如 | rm -rf / 等恶意载荷）。
强制服务与目录白名单机制：
Agent (LLM) 传入的只能是 service 名称（如 "gateway"），绝不能是绝对路径。
必须通过 config.py 读取的 services.<service_name>.log_paths 将名称映射到物理路径。如果服务不存在于配置中，立刻返回 isError=True 的结果。
返回结果大小熔断 (Truncation)：
日志文件动辄几十 GB，绝不能将所有匹配结果全部读入内存或返回给 Client（会导致上下文溢出）。
必须严格遵守 Roadmap 中的 limit（如最多 50 条）和 max_bytes（如 64KB）限制。
当发生截断时，在返回的结构化 JSON 中明确标记 "truncated": true，这能提示调用 Probe 的 LLM 缩小时间范围或增加特定关键字。
四、 Tool 设计与返回值规范
暴露意图，而非底层命令：
暴露给 LLM 的 Tool 描述必须清晰。例如 search_logs 的 description 应该写明：“根据服务名称、时间范围和关键字检索日志，用于排查报错”
。良好的描述能帮助模型准确判断何时该调用哪个 Tool。
返回结构化的可观测数据：
Roadmap 要求返回 JSON。在 MCP 协议中，Tool 返回的 content 是一个数组，你需要将结构化的结果（包含 summary, items, next_actions 等）序列化为格式化的 JSON 字符串放进 TextContent 中
。
高阶技巧：除了将其序列化为文本放入 content 数组，还可以将其作为原生的 JSON Object 放入 MCP 协议规范的 structuredContent 字段中（此举更符合 MCP 的最新最佳实践，方便客户端提取）
。
五、 落地路径拆解 (给 AIAgent 的行动顺序)
建议你按照 Roadmap 中的 11. 开发顺序建议 稳扎稳打：
Phase 1 骨架搭建：先不要写任何真实的日志查询逻辑。写出 main.py，配置好 FastMCP，提供一个只返回假数据的 list_services 工具，并通过 MCP Inspector 跑通本地测试
。
Phase 2-4 核心逻辑：逐个实现 search_logs（按服务和时间搜索）、search_by_request_id（链路追踪）和 context_around_match（获取某报错前后的 10 行上下文以推断根本原因）。
Phase 5 安全与脱敏：最后在 log_service.py 中接入脱敏功能（使用正则替换手机号/Token等），并写入拦截与审计日志。
总结： 不要尝试去实现一个“全能”的 Shell 工具。你的目标是实现一个高度结构化的“数字探针”，它只懂得按照固定的规则（如 grep 指定目录）安全地拿回文本片段，剩下的推理工作将交由上层连接这个 MCP 的 LLM 来完成。
