# Bark Notify for Codex

Codex 任务完成后发送一条 Bark 通知：设备名称为标题、工作区名称为副标题，正文包含用户请求和完整最终回复。通知使用普通正文，隐藏本地链接地址和内部展示指令，保留明确的 HTTP/HTTPS 网页地址。

## 在每台电脑上安装

需要 Git 和 Python 3.9+。这是公开仓库，下载、克隆和拉取更新无需登录 GitHub；提交并推送修改仍需仓库写入权限。

仓库地址：https://github.com/BatuQI/bark-notify

克隆地址：`https://github.com/BatuQI/bark-notify.git`

1. 将仓库克隆到本机 `$CODEX_HOME/skills/bark-notify`；未设置 `CODEX_HOME` 时为 `~/.codex/skills/bark-notify`。这样 Skill 目录就是 Git 工作副本，拉取更新后直接使用新代码。
2. 若该目录已存在但不是 Git 仓库，先把旧目录备份到 `skills` 之外，再克隆；把旧的 `config.json` 复制回新目录。已有本仓库的工作副本直接更新即可。
3. 首次安装时，将 `config.example.json` 复制为 `config.json`，填入自己的 Bark key。也可在本机用 `BARK_DEVICE_KEY` 环境变量覆盖 key。模板不包含接收端密钥；每台电脑的 `config.json` 被 Git 忽略，不会被提交或被拉取覆盖。
4. 在 Skill 目录运行以下命令，启用全局默认要求：

```text
python -X utf8 scripts/install.py --enable-default
```

macOS/Linux 通常使用 `python3`；Windows 也可使用 `py -3`。重启 Codex 或新建聊天以加载全局要求。

设备名自动读取本机，工作区按当前任务确定，不需要把来源电脑的用户名或路径写进配置。

## 多台电脑同步

建议选择一台电脑维护代码，修改后提交并推送到 GitHub。其他电脑在各自的 Skill 目录拉取：

```text
git pull --ff-only
python -X utf8 scripts/install.py --enable-default
```

第二条命令刷新该电脑的全局规则，保留已有无关指令。仅使用 `--ff-only` 拉取：分支分叉时停止，不自动重置、覆盖或隐藏本地修改。拉取失败时先解决失败原因，再重新执行安装命令。

要自动拉取，可让每台电脑的定时任务或 Codex 自动化定期执行上述流程，并且仅在拉取成功后刷新规则。GitHub 保存版本，电脑需要主动拉取；离线时不能获取新版本。自动化的频率应按各台电脑的使用习惯配置。

## 本地配置

- `config.json`：当前电脑的接收端和个人设置，不进入 Git。
- `config.example.json`：不含 key 的配置模板，随代码同步。
- `ttl=600` 表示历史消息保留 10 分钟，可以在本机配置中调整。
- 不要将含个人配置的 ZIP、全局 AGENTS.md 或聊天记录提交到仓库。

完整使用与停用说明见 [references/setup.md](references/setup.md)。
