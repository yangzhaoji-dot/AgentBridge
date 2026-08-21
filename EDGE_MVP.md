# AgentBridge v0.1：Edge + ChatGPT 网页 + Codex

目标链路：

```text
Codex --MCP ask_chatgpt(prompt)--> AgentBridge :8765
      --WebSocket--> Edge 扩展 --DOM--> 已登录的 chatgpt.com
      <--完整回答---------------------------------------
```

## 第一次安装 Edge 扩展

1. 双击项目中的 `Start-AgentBridge.ps1`，或在 PowerShell 中运行：

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-AgentBridge.ps1
   ```

2. 在 Edge 地址栏打开 `edge://extensions`。
3. 打开左侧或页面上的“开发人员模式”。
4. 点击“加载解压缩的扩展”。
5. 选择这个目录：

   ```text
   C:\Users\yangz\Documents\Codex\web-local-agent\extension
   ```

6. 打开一个已登录的 `https://chatgpt.com/` 标签页。扩展图标显示 `ON` 表示连接成功。

扩展自动从 `127.0.0.1:8765` 获取本机随机令牌。服务只监听本机，WebSocket 还会校验 `chrome-extension://` Origin。

## Codex MCP 配置

项目的 `.codex/config.toml` 已包含：

```toml
[mcp_servers.agentbridge]
url = "http://127.0.0.1:8765/mcp"
tool_timeout_sec = 240
default_tools_approval_mode = "prompt"
```

从本项目目录启动 Codex，使用 `/mcp` 应能看到 `agentbridge` 和 `ask_chatgpt`。

## 第一次闭环测试

在 Codex 中明确要求：

```text
请调用 ask_chatgpt 工具，询问：1+1等于多少？只回复答案。
```

预期结果：

```text
Codex tool call
→ Edge 扩展把问题写入专用 ChatGPT 标签页
→ ChatGPT 回复 2
→ ask_chatgpt 工具向 Codex 返回 2
```

## 当前限制

- 只支持一个 Edge 扩展连接、一个专用 ChatGPT 标签页和一个并发请求。
- 只支持纯文本，返回完整回答，不提供流式增量。
- ChatGPT 网页 DOM 更新后，`chatgpt_adapter.js` 的选择器可能需要调整。
- 不要在 prompt 中发送密码、API Key、私有文件内容或其他敏感数据。
