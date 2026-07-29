# GitLab Issue 使用说明

## 目录

- [统一入口](#统一入口)
- [目标项目解析](#目标项目解析)
- [令牌与环境文件](#令牌与环境文件)
- [命令](#命令)
- [更新语义](#更新语义)
- [安全与错误处理](#安全与错误处理)

## 统一入口

始终优先调用 skill 自带的入口：

```bash
/absolute/path/to/gitlab-issue/scripts/run.sh <command> [arguments...]
```

入口优先使用 skill 自己的 `.venv`，其次使用 `PYTHON` 指定的解释器，再回退到系统 `python3` 或 `python`。缺少依赖时执行：

```bash
/absolute/path/to/gitlab-issue/scripts/run.sh bootstrap
```

## 目标项目解析

本 skill 只管理当前自托管 GitLab 仓库。必须从目标仓库根目录运行：

```bash
git remote get-url origin
```

脚本从 `origin` 提取项目路径，但不从 origin 信任任意 API 地址。受信任实例必须通过 `GITLAB_BASE_URL` 显式配置。

支持以下 origin：

```text
https://gitlab.example.com/group/project.git
git@gitlab.example.com:group/project.git
ssh://git@gitlab.example.com:2222/group/project.git
```

校验规则：

- HTTP(S) origin：协议、主机和有效端口必须与 `GITLAB_BASE_URL` 一致。
- SSH origin：主机名必须与 `GITLAB_BASE_URL` 一致；SSH 端口不等同于 GitLab Web 端口，因此不比较端口。
- `GITLAB_BASE_URL` 必须是 `http(s)://host[:port]`，不得包含凭据、查询参数、fragment 或子路径。
- GitHub、GitLab.com、Bitbucket、Codeberg 与 Gitea 的公共托管主机被直接拒绝。
- 项目路径始终来自当前 origin，不接受另一个项目的覆盖参数。
- 任一校验失败都在读取 `GITLAB_PRIVATE_TOKEN` 和请求 API 前终止。

## 令牌与环境文件

使用两个变量：

```dotenv
GITLAB_BASE_URL=https://gitlab.example.com
GITLAB_PRIVATE_TOKEN=
```

已导出的环境变量优先级最高。随后按以下顺序加载存在的 `.env`，且低优先级文件不覆盖高优先级值：

1. 当前工作目录 `.env`
2. skill 根目录 `.env`
3. `scripts/.env`

`GITLAB_BASE_URL` 是受信任实例边界，不要临时改成与当前仓库无关的主机。不得提交真实令牌，不得在命令参数、日志、issue 正文或评论中输出令牌。

## 命令

创建：

```bash
run.sh create --title "修复数据校验" --labels "(高),data" --body-file /tmp/issue.md
```

读取与列出：

```bash
run.sh read --iid 40
run.sh read --iid 40 --notes --notes-limit 50
run.sh list --state opened --search "PIT" --labels "data" --limit 100
```

更新与评论：

```bash
run.sh update --iid 40 --title "新标题"
run.sh update --iid 40 --labels "(中),文档"
run.sh update --iid 40 --append --body-file /tmp/update.md
run.sh update --iid 40 --state-event close
run.sh comment --iid 40 --body-file /tmp/comment.md
```

删除评论与 issue：

```bash
run.sh delete-note --iid 40 --note-id 1234
run.sh delete --iid 40 --yes
```

## 更新语义

- `--labels`：把标签完整替换为给定集合。
- `--append`：读取现有 description，以空行分隔后追加新内容。
- `--body` 或 `--body-file`：不带 `--append` 时完整替换 description。
- `--state-event close|reopen`：关闭或重开 issue。

需要补充标签时，先读取 issue，并把已有标签与新增标签一起传给 `--labels`。所有待写入标签必须已存在于目标项目。

## 安全与错误处理

- 在任何写操作前核对目标项目。
- 当前仓库不是已配置的自托管 GitLab 项目时停止，不使用本 skill。
- 不通过修改 origin、伪造 `GITLAB_BASE_URL` 或调用底层函数绕过实例校验。
- 删除评论和 issue 必须已有用户明确授权；删除 issue 还必须传 `--yes`。
- 清理评论前，把仍有效的决定并入 description 或保留的最终评论。
- 若 GitLab 实例不支持删除 issue，或令牌权限不足，改用关闭 issue；不要把关闭描述成删除。
- 网络、认证和 GitLab API 错误会以简洁错误信息返回，并使用非零退出码。
