# CoPaw 迁移验证样例

本文档提供迁移自 CoPaw 的 skills 与 tools 的验证样例，用于确认迁移成功后行为符合预期。

## 一、Skills 验证

### 1. file_reader

- **预期**：agent 能根据 skill 只对纯文本类文件（.txt/.md/.json/.yaml/.csv 等）做读取与总结，并知道 PDF/Office 等由其他 skill 处理。
- **验证步骤**：
  1. 在 workspace 下放一个 `test.txt`，内容若干行。
  2. 启动 `nanobot agent`，输入：`读一下 test.txt 并总结主要内容。`
  3. 应能读到文件并给出总结；若提到「用 read_file」或先探测类型再读，说明 skill 生效。

### 2. news

- **预期**：当用户问「今日新闻」「某类新闻」时，agent 知道用浏览器打开文档中列出的新闻站 URL 并抓取摘要。
- **验证步骤**：
  1. 启动 `nanobot agent`，输入：`今天科技类有什么新闻？` 或 `看看人民网头条。`
  2. 若配置了 browser 类能力（如 MCP browser），应尝试打开对应 URL 并总结；若未配置 browser，可能回复需浏览器能力——说明 skill 已被加载并引用正确来源。

### 3. browser_visible

- **预期**：当用户明确要求「可见浏览器」「有界面的浏览器」时，agent 知道应以 headed 模式启动浏览器。
- **验证步骤**：
  1. 输入：`用有界面的浏览器打开 https://example.com。`
  2. 若已接浏览器能力，应看到使用 headed 或类似参数的说明/调用；说明 skill 被选中并指导了行为。

### 4. xlsx

- **预期**：涉及 .xlsx/.csv 等表格文件时，agent 使用 xlsx skill 的规范（字体、公式零错误、颜色约定等）。
- **验证步骤**：
  1. 准备一个 `data.csv`，输入：`把这个 csv 转成 xlsx，并加一列「备注」。`
  2. 应生成或编辑表格文件，且回复/文件中体现 skill 中的规范（如无 #REF! 等）。

### 5. pptx

- **预期**：涉及 .pptx 创建/编辑/解析时，agent 使用 pptx skill（含依赖说明：LibreOffice、Poppler）。
- **验证步骤**：
  1. 输入：`用当前目录的 template.pptx 做一份 3 页的演示文稿，标题为「迁移验证」。`
  2. 若有 template.pptx 且环境有 soffice/pdftoppm，应产出 pptx；否则可能提示缺少依赖——说明 skill 被加载。

### 6. pdf

- **预期**：涉及 PDF 读写/合并/表单等时，agent 使用 pdf skill。
- **验证步骤**：
  1. 输入：`把 a.pdf 和 b.pdf 合并成一个 pdf。` 或 `从 report.pdf 里摘出前两页的文本。`
  2. 应按 skill 推荐方式（如 pypdf）操作或提示缺少文件/依赖。

### 7. docx

- **预期**：涉及 Word 文档创建/编辑时，agent 使用 docx skill。
- **验证步骤**：
  1. 输入：`写一份一页的 Word 文档，标题「迁移验证」，正文几段说明即可。`
  2. 应产出 .docx 或说明需要 LibreOffice 等依赖——说明 skill 被引用。

---

## 二、Tools 验证

### 1. get_current_time

- **验证**：在 agent 对话中请求当前时间，例如：`现在几点了？` 或 `当前系统时间？`
- **预期**：agent 调用 get_current_time，返回带时区的本地时间字符串（如 `2026-02-28 12:00:00 CST (UTC+0800)`）。

### 2. grep_search

- **验证**：在 workspace 有若干 .py 文件时，输入：`在项目里搜索包含 "def execute" 的代码行。`
- **预期**：agent 调用 grep_search(pattern="def execute", path=workspace)，返回 path:line_no: content 格式的结果。

### 3. glob_search

- **验证**：输入：`列出当前项目里所有 .md 文件。` 或 `找一下 **/*.json。`
- **预期**：agent 调用 glob_search(pattern="*.md" 或 "**/*.json", path=workspace)，返回匹配路径列表。

### 4. memory_search

- **前提**：workspace 下存在 `memory/MEMORY.md`（或 memory/*.md），且其中有若干可识别文本。
- **验证**：输入：`在记忆里查一下和「迁移」相关的内容。` 或 `memory 里有没有记过关于 xlsx 的说明？`
- **预期**：agent 调用 memory_search(query="迁移" 或 "xlsx")，返回 MEMORY.md / memory/*.md 中匹配行及路径、行号。

### 5. send_file

- **前提**：当前为 channel 会话（如 CLI 或已配置的 channel），且 channel 支持 media。
- **验证**：先让 agent 生成一个文件（如 `写一个 hello.txt 内容为 Hello`），再请求：`把这个 hello.txt 发给我。`
- **预期**：agent 调用 send_file(path="hello.txt")，当前会话应收到该文件（或媒体附件）；若 channel 不支持附件，可能返回错误说明。

---

## 三、快速自检命令（可选）

在项目根目录、已安装依赖（如 `pip install -e .` 或 `uv run`）的环境下，可做一次工具存在性检查（不依赖 LLM）：

```bash
cd /path/to/nanobot
# 若使用 venv/uv：先激活环境或使用 uv run python
python -c "
from pathlib import Path
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.time import GetCurrentTimeTool
from nanobot.agent.tools.search import GrepSearchTool, GlobSearchTool
from nanobot.agent.tools.memory_search import MemorySearchTool
from nanobot.agent.tools.send_file import SendFileTool

w = Path('.').resolve()
r = ToolRegistry()
r.register(GetCurrentTimeTool())
r.register(GrepSearchTool(workspace=w))
r.register(GlobSearchTool(workspace=w))
r.register(MemorySearchTool(workspace=w))
r.register(SendFileTool())
assert 'get_current_time' in r.tool_names
assert 'grep_search' in r.tool_names
assert 'glob_search' in r.tool_names
assert 'memory_search' in r.tool_names
assert 'send_file' in r.tool_names
print('All migrated tools registered OK.')
"
```

Skills 是否加载可在 agent 启动后看 system prompt 中的 `<skills>` 片段是否包含 file_reader、news、browser_visible、xlsx、pptx、pdf、docx 等条目。
