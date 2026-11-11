# 安装与配置

通知脚本依赖 Python 3.9+，无需第三方包，支持 Windows、macOS、Linux。Git 仓库与通用安装包只提供不含 key 的 `config.example.json`；用户配置保存在本地 `config.json`，也可用 `BARK_DEVICE_KEY` 环境变量覆盖 key。设备名称在发送时读取；不要将含 key 的配置或个人 ZIP 提交到 Git。

通过 Git 安装和同步时，参阅 [README.md](../README.md)，优先将仓库直接克隆到本机 Skill 安装目录。每台电脑的 `config.json` 被 `.gitignore` 忽略，拉取只更新已提交的代码和说明。

## 首次配置与通知规则

推荐在终端运行 `npx --yes github:BatuQI/bark-notify`；需要 Node.js 18+、Git、Python 3.9+。安装提示词见 [INSTALL_PROMPT.md](../INSTALL_PROMPT.md)。

只有没有 `config.json` 的首次安装才进入向导，提示服务地址、key、分组、保留时间、内容格式、是否附上任务回复、是否清理显示，以及通知范围。推荐保留一天（86400 秒），普通正文，包含完整回复并清理显示；用户可以修改。通知范围可选仅明确调用、每个任务结束（成功、失败、取消或被拦截）或自定义条件。默认仅明确调用，不自动替用户启用全局通知。

Codex 的非交互工具应先收集用户选择，写入系统临时目录的 JSON，再传 `--config-file <文件>`；用户选择每个任务结束才加 `--enable-default`，自定义条件使用 `--rule-file <UTF-8文件>`，仅明确调用不加规则参数。安装后删除临时配置与规则文件。不要将 key 放在 shell 参数中。

已有本地配置时，不论重复安装还是手动更新，都直接沿用且不重问。已有全局 Bark 规则（包括用户编辑过的内容）原样保留；安装器不再重写已有标记块。用户以后明确要求改配置或触发范围时，可编辑本机 `config.json` 或全局规则。

首次选择全局通知时，会加入带 `bark-notify:begin/end` 标记的规则，并写入本机安装路径。优先使用非空的 `AGENTS.override.md`，否则使用 `AGENTS.md`；保留无关指令，写入前备份。规则按用户选择的内容选项与范围发送，不把普通正文、完整回复或所有任务强加给其他使用者。

## 不使用 npx 的安装方式

直接将仓库克隆到 `$CODEX_HOME/skills/bark-notify`（默认 `~/.codex/skills/bark-notify`），进入目录运行 `python -X utf8 scripts/install.py`。macOS/Linux 通常用 `python3`，Windows 也可用 `py -3`。首次交互配置流程相同。

ZIP 用户解压后运行同一 Python 命令，会复制到目标 Skill 目录，跳过来源机器的配置、Git 元数据和缓存。`--skill-dir` 可指定完整目标目录。不覆盖已有目标；更新旧 ZIP 安装时先备份到 skills 目录之外，替换代码后迁移原本的 `config.json`，保留本机全局规则。已有配置不要重新生成。

## 手动更新

用户需要更新时运行 `npx --yes github:BatuQI/bark-notify --update`，或在已安装的 Git 工作副本中运行 `git pull --ff-only`。只快进更新代码，保留 `config.json` 和全局自定义规则；不再次询问配置，不改变已有保留时间，不重新调用 `--enable-default`，不建立定时任务或后台更新。代码有本地改动、冲突或分叉时交由用户处理，不强制覆盖。

安装或更新后重启 Codex 或新建聊天加载。是否发送本次安装任务完成通知也遵循用户已选择并授权的规则，不额外发送测试通知。

这是由 Codex 遵循指令调用的 Skill，不是后台监控或进程退出钩子。取消或被拦截的任务已结束且 Codex 仍可执行工具时，按用户范围发送如实的最终结果；不继续原任务或绕过限制。强制停止、进程退出导致无法执行工具，或网络不可用时，不能保证通知，也不在后台补发。若项目明确覆盖全局要求，以当前有效指令为准。

用户选择每个任务结束时，成功、失败、取消或被拦截都属于结果，也适用于只读任务和 `create_thread` 创建的独立聊天；自定义范围及本机已有规则仍以用户条件为准。等待输入、等待审批、仍在执行或修复中不发送；审批或执行被拒绝且任务就此结束才按范围通知。同一次结束只尝试一次，不因等待、刷新或继续输出重复发送。只有 `collaboration.spawn_agent` 等启动的会话内子代理不单独发送。通知 JSON 使用系统临时目录，不修改只读任务的项目文件。

## 通知格式与配置

| 参数 | 内容 |
| --- | --- |
| `title` | 发送时的电脑设备名称 |
| `subtitle` | 当前任务工作区根目录名，例如 `PersonalWork` |
| `body` | 一条普通正文通知，包含“你的请求”和“任务回复”两段 |
| `group` | `example`，与测试命令一致 |
| `ttl` | 首次推荐 `86400` 秒，即一天；已有配置按原值保留，不是网络超时 |

在安装目录的 `config.json` 修改 `server`、`device_key`、`group`、`ttl`、`content_format`、`include_reply`、`readable_body`。`server` 是不含 key 的 HTTPS 服务地址，默认 `https://api.day.app`。也可用环境变量 `BARK_SERVER`、`BARK_DEVICE_KEY` 覆盖。`BARK_DEVICE_NAME` 用于指定设备名称，适合容器或远程环境。

### 用户原文和完整最终回复

默认 `include_reply=true`，由脚本组合成一条通知：

```text
【你的请求】
用户本次任务原文

【任务回复】
Codex 的完整最终回复
```

输入 JSON 保存完整请求和回复，不摘要、不截断。多条用户消息先以两个换行拼接。默认 `readable_body=true`，脚本生成适合手机阅读的正文：本地文件链接只保留名称，独立本地路径缩短为文件名；明确的 HTTP/HTTPS 网页链接显示为“名称 (网址)”，独立网页地址保留；移除内部聊天/代码评论展示指令，并去掉回复中的加粗、标题、代码围栏等标记。源文本和聊天回复不变，只有通知显示会变化。关闭 `readable_body` 可恢复完全原始格式。

两段标签和分隔换行是固定格式，不属于原文。发送前先定稿最终回复，成功发送后在聊天中逐字输出 JSON 内的原始回复，不追加通知状态。若发送失败，则在聊天回复中说明失败，不自动重试。

需要恢复旧版仅用户原文的格式时，将 `include_reply` 改为 `false`。旧配置没有该字段时也保持仅原文行为；开启后缺少 `reply` 会报错，不会悄悄省略任务回复。

### body 换行是否需要 Markdown

不需要。自动通知使用 `--messages-file` 读取 UTF-8 JSON，再由 JSON 编码器构建请求，支持中文、引号、反斜杠、emoji、`&`、LF 和 CRLF。例如：

```json
{"messages":["用户原文第一行\n第二行\n"],"reply":"这是完整最终回复。"}
```

该示例原文自带一个末尾换行，因此保留字符串末尾的 `\n`；没有末尾换行的原文不应添加它。JSON 文档本身结尾由编辑器补上的换行不进入字符串，因此不会多出通知正文换行。多个消息以两个换行拼接；除删除内部展示指令及其专用分隔空行等显示转换外，不裁剪原文空白。禁止用 `strip()`、`rstrip()` 或删除最后一个换行来修正文案。

JSON 字符串中的 `\n`、`\r\n` 在解析后恢复为真实换行；不要二次转义，不要用 shell 字符串拼接正文。旧 `--body-file` 仅供旧的仅原文模式兼容，不用于新的自动通知。成功输出的 `request_sha256`、`reply_sha256` 对应原始输入，`display_request_sha256`、`display_reply_sha256` 对应通知分段，`body_sha256` 对应整条提交正文。显示清理开启时，原文与通知摘要允许不同，不能再将两者描述为逐字一致。

默认使用普通正文，不启用 Markdown 渲染，配置为：

```json
"content_format": "body"
```

此时只发送 `body` 字段。只有用户明确要求 Markdown 渲染时才改为 `markdown`，脚本届时只发送 `markdown` 字段。Bark 文档说明 `markdown` 会覆盖 `body`，且原始 Markdown 排版会被渲染。

脚本使用 `POST /push` JSON，key 位于请求体。单次请求超时 15 秒，不自动重试。只在 HTTP 成功且 Bark `code=200` 时报告成功，这表明接口接受，不能证明手机已展示。原文及完整回复不截断、不拆分；若服务拒绝超长内容则报告失败，不擅自改为摘要。

## 停用

在安装时提示的全局 `AGENTS.md` 或 `AGENTS.override.md` 中删除从 `<!-- bark-notify:begin -->` 到 `<!-- bark-notify:end -->` 的整段规则，然后重启 Codex 或新建聊天。Skill 可保留用于明确调用。

## 参考

- [Bark 使用教程](https://bark.day.app/#/tutorial)
- [Bark 参数](https://bark.day.app/#/params)
- [官方教程源码：JSON POST 与 /push](https://github.com/Finb/Bark/blob/master/docs/tutorial.md)
- [Codex 全局 AGENTS.md 指令](https://developers.openai.com/codex/guides/agents-md/)
- [Codex Skill 文档](https://developers.openai.com/codex/skills/)
