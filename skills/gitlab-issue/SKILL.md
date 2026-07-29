---
name: gitlab-issue
description: 统一管理当前自托管 GitLab 仓库的 issue，支持创建、读取、检索、更新、评论、关闭、重开及删除，并在发送访问令牌前强制校验当前 origin 与受信任 GitLab 实例一致。仅适用于当前仓库确实托管在已配置自托管 GitLab 上时使用。
---

# GitLab Issue

## 概述

使用本 skill 的统一入口管理当前仓库的 GitLab issue。通过 `GITLAB_BASE_URL` 声明受信任的自托管 GitLab 实例，只从当前仓库 `origin` 提取项目路径。

本 skill 不适用于 GitHub、Gitea、Bitbucket 或与 `GITLAB_BASE_URL` 不一致的仓库，也不用于跨项目操作。

## 工作流

1. 在目标仓库根目录执行命令，确认其 `origin` 指向自托管 GitLab。
2. 通过环境变量或受支持的 `.env` 配置：
   - `GITLAB_BASE_URL`：受信任的自托管 GitLab 实例根地址。
   - `GITLAB_PRIVATE_TOKEN`：具备所需 issue API 权限的令牌。
3. 让脚本先校验目标。
   - HTTP(S) origin 的协议、主机和有效端口必须与 `GITLAB_BASE_URL` 一致。
   - SSH origin 的主机名必须与 `GITLAB_BASE_URL` 一致。
   - 校验失败时必须在读取 token 和调用 API 前终止，不得绕过。
4. 对修改操作先读取现状。
   - 改标签前判断是补充还是完整替换；补充时先读取并保留现有标签。
   - 改 description 前判断是追加还是完整覆盖；追加时使用 `--append`。
   - 删除评论或 issue 前保留仍有效的结论，并取得用户明确授权。
5. 使用 [scripts/run.sh](scripts/run.sh) 作为统一入口。
6. 检查脚本输出的 `iid`、`state`、`web_url` 等字段，确认操作落在预期项目。

## 命令模式

从目标自托管 GitLab 仓库根目录执行：

```bash
/absolute/path/to/gitlab-issue/scripts/run.sh list --state opened
/absolute/path/to/gitlab-issue/scripts/run.sh read --iid 40 --notes
/absolute/path/to/gitlab-issue/scripts/run.sh create --title "..." --labels "(高),data" --body-file /tmp/issue.md
/absolute/path/to/gitlab-issue/scripts/run.sh update --iid 40 --labels "(中),文档" --append --body-file /tmp/update.md
/absolute/path/to/gitlab-issue/scripts/run.sh comment --iid 40 --body "已完成"
```

破坏性命令必须显式确认：

```bash
/absolute/path/to/gitlab-issue/scripts/run.sh delete-note --iid 40 --note-id 1234
/absolute/path/to/gitlab-issue/scripts/run.sh delete --iid 40 --yes
```

首次使用或依赖缺失时执行：

```bash
/absolute/path/to/gitlab-issue/scripts/run.sh bootstrap
```

## 资源使用

- 查看完整参数、目标解析、`.env` 优先级和安全规则：[references/usage.md](references/usage.md)
- 执行稳定流程：[scripts/run.sh](scripts/run.sh)
- 安装隔离依赖：[scripts/bootstrap.sh](scripts/bootstrap.sh)
- 直接维护 API 实现：[scripts/gitlab_issue.py](scripts/gitlab_issue.py)

## 输出规则

- 返回 JSON，供人工核对或后续工具处理。
- 不输出访问令牌或带令牌的请求头。
- origin 与 `GITLAB_BASE_URL` 不匹配时以非零退出码终止，不发送令牌。
- 只允许使用目标项目中已经存在的标签，不隐式创建标签。
- 修改 description 或标签前先读取现状，避免意外覆盖。
- 删除失败且实例不支持删除时，说明限制并优先建议关闭 issue，不伪报成功。
