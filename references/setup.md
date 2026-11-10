# 安装与配置

依赖 Python 3.9+，无需第三方包，支持 Windows、macOS、Linux。Git 仓库仅提供不含 key 的 `config.example.json`；首次克隆时复制为 `config.json`，填写本机使用的接收端 key，或用 `BARK_DEVICE_KEY` 环境变量覆盖。个人安装包可包含用户提供的 `config.json`，供自己的电脑间复制。设备名称在发送时读取；不要将含 key 的配置或个人 ZIP 提交到 Git。

通过 Git 安装和同步时，参阅 [README.md](../README.md)，优先将仓库直接克隆到本机 Skill 安装目录。每台电脑的 `config.json` 被 `.gitignore` 忽略，拉取只更新已提交的代码和说明。

## 安装并设为默认

解压后，终端进入 `bark-notify` 文件夹。Windows：

```powershell
python .\scripts\install.py --enable-default
```

若只有 Python Launcher，将 `python` 换成 `py -3`。macOS / Linux：

```sh
python3 ./scripts/install.py --enable-default
```

默认复制至 `$CODEX_HOME/skills/bark-notify`；未设置时为 `~/.codex/skills/bark-notify`。`--skill-dir` 可指定完整目标目录，如 `~/.agents/skills/bark-notify`。不覆盖已有目标；已有安装要重新启用默认规则，请在已安装目录运行安装脚本。

`--enable-default` 会向全局指令加入带 `bark-notify:begin/end` 标记的规则，并写入本机安装路径，即使 Skill 不在发现列表中，也能直接读取。优先更新已存在且非空的 `AGENTS.override.md`，否则更新 `AGENTS.md`。保留原有指令，修改前自动保存 `.bark-backup-时间戳` 备份，重复启用不会重复追加。不加该参数则只安装。

安装后重启 Codex 或新建聊天，让 Skill 和全局要求加载。可要求 Codex“完成这个任务后，按全局要求发送 Bark 通知”验证。

这是由 Codex 遵循指令调用的 Skill，不是后台监控或进程退出钩子。强制退出、任务取消或网络不可用不会补发。若项目明确覆盖全局要求，以当前有效指令为准。

默认要求也适用于只读任务，以及由 `create_thread` 创建的独立聊天；独立聊天的委派启动标记不表示会话内子代理。只有 `collaboration.spawn_agent` 等启动的会话内子代理不单独发送。通知 JSON 使用系统临时目录，不修改只读任务的项目文件。

## 通知格式与配置

| 参数 | 内容 |
| --- | --- |
| `title` | 发送时的电脑设备名称 |
| `subtitle` | 当前任务工作区根目录名，例如 `PersonalWork` |
| `body` | 一条普通正文通知，包含“你的请求”和“任务回复”两段 |
| `group` | `example`，与测试命令一致 |
| `ttl` | `600`，归档消息保留 600 秒，不是网络超时 |

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
