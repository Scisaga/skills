from __future__ import annotations

"""
skills/gitlab-issue/scripts/gitlab_issue.py

业务目的
- 统一管理当前仓库对应 GitLab 项目的 issue：创建、读取、列表、更新、评论、删除评论、删除。

安全约束（AGENTS.md）
- 不在日志/输出中打印 token。

默认约定
- 启动时按当前工作目录、skill 根目录、脚本目录的顺序加载 `.env`，再读取
  `GITLAB_BASE_URL` 与 `GITLAB_PRIVATE_TOKEN`。
- `GITLAB_BASE_URL` 必须指向当前自托管 GitLab 实例。
- 项目路径只从 `git remote get-url origin` 推导；origin 与配置的 GitLab
  实例不匹配时，在读取 token 和发送 API 请求前拒绝执行。

示例
- 创建 issue：
  /absolute/path/to/gitlab-issue/scripts/run.sh create \\
    --title "fix(api): 修正 issue CLI 输出" \\
    --labels "(高),data" \\
    --body-file .tmp/gitlab_issue_body.md

- 读取 issue（包含评论）：
  /absolute/path/to/gitlab-issue/scripts/run.sh read --iid 40 --notes

- 列出全部 issue：
  /absolute/path/to/gitlab-issue/scripts/run.sh list --state all

- 更新 issue description：
  /absolute/path/to/gitlab-issue/scripts/run.sh update \\
    --iid 40 \\
    --labels "(中),文档" \\
    --body-file .tmp/gitlab_issue_body.md

- 追加到既有 description：
  /absolute/path/to/gitlab-issue/scripts/run.sh update \\
    --iid 40 \\
    --append \\
    --body-file .tmp/gitlab_issue_body.md

- 回复 issue：
  /absolute/path/to/gitlab-issue/scripts/run.sh comment \\
    --iid 40 \\
    --body "已完成实现，等待验收。"

- 删除 issue 评论：
  /absolute/path/to/gitlab-issue/scripts/run.sh delete-note \\
    --iid 40 \\
    --note-id 1234

- 删除 issue：
  /absolute/path/to/gitlab-issue/scripts/run.sh delete --iid 40 --yes
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


_BASE_URL_ENV = "GITLAB_BASE_URL"
_TOKEN_ENV = "GITLAB_PRIVATE_TOKEN"
_REQUEST_TIMEOUT = 30
_HOSTED_FORGE_HOSTS = {
    "bitbucket.org",
    "codeberg.org",
    "gitea.com",
    "github.com",
    "gitlab.com",
}


@dataclass(frozen=True)
class GitlabTarget:
    base_url: str
    project_path: str


def _ensure_runtime_dependencies() -> None:
    missing: list[str] = []
    if requests is None:
        missing.append("requests")
    if load_dotenv is None:
        missing.append("python-dotenv")
    if missing:
        raise RuntimeError(
            "缺少 Python 依赖："
            + ", ".join(missing)
            + "。请先执行 skills/gitlab-issue/scripts/run.sh bootstrap"
        )


def _load_repo_dotenv() -> None:
    """
    按仓库约定加载 `.env`，不覆盖调用方或更高优先级文件已经设置的变量。
    """
    if load_dotenv is None:
        raise RuntimeError("缺少 Python 依赖 python-dotenv")

    script_dir = Path(__file__).resolve().parent
    skill_root = script_dir.parent
    candidates = [
        Path.cwd() / ".env",
        skill_root / ".env",
        script_dir / ".env",
    ]
    seen: set[Path] = set()
    for env_path in candidates:
        resolved = env_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if env_path.exists():
            load_dotenv(env_path, override=False)


def _run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return (proc.stdout or "").strip()


def _strip_git_suffix(project_path: str) -> str:
    normalized = project_path.strip().strip("/")
    if normalized.endswith(".git"):
        normalized = normalized[: -len(".git")]
    if not normalized:
        raise RuntimeError("无法从当前仓库 origin 推导 GitLab 项目路径")
    return normalized


def _load_base_url() -> str:
    raw = os.getenv(_BASE_URL_ENV)
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError(
            f"未配置 {_BASE_URL_ENV}。请把当前自托管 GitLab 实例地址写入环境变量或 .env"
        )

    base_url = raw.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError(f"{_BASE_URL_ENV} 必须是有效的 http(s) 地址")
    try:
        parsed.port
    except ValueError as exc:
        raise RuntimeError(f"{_BASE_URL_ENV} 包含无效端口") from exc
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError(f"{_BASE_URL_ENV} 不得包含凭据、查询参数或 fragment")
    if parsed.path not in {"", "/"}:
        raise RuntimeError(f"{_BASE_URL_ENV} 当前仅支持不带子路径的 GitLab 实例地址")
    normalized_host = str(parsed.hostname).lower().rstrip(".")
    hosted_forge = next(
        (
            host
            for host in _HOSTED_FORGE_HOSTS
            if normalized_host == host or normalized_host.endswith(f".{host}")
        ),
        None,
    )
    if hosted_forge:
        raise RuntimeError(
            f"{_BASE_URL_ENV} 必须指向自托管 GitLab，不能使用托管代码平台 {normalized_host}"
        )
    return base_url


def _http_endpoint(parsed: Any) -> tuple[str, str, int]:
    scheme = str(parsed.scheme or "").lower()
    host = str(parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("URL 包含无效端口") from exc
    effective_port = int(port or (443 if scheme == "https" else 80))
    return scheme, host, effective_port


def _origin_target(*, base_url: str) -> GitlabTarget:
    """从当前仓库 origin 提取项目路径，并验证它属于配置的 GitLab 实例。"""
    origin = _run(["git", "remote", "get-url", "origin"]).strip()
    if origin.endswith(".git"):
        origin = origin[: -len(".git")]

    configured = urlsplit(base_url)
    configured_host = str(configured.hostname or "").lower().rstrip(".")

    if origin.startswith(("http://", "https://")):
        parsed_origin = urlsplit(origin)
        if parsed_origin.username or parsed_origin.password:
            raise RuntimeError("当前仓库 origin 不得包含内嵌凭据")
        origin_endpoint = _http_endpoint(parsed_origin)
        configured_endpoint = _http_endpoint(configured)
        if not origin_endpoint[1] or not parsed_origin.path:
            raise RuntimeError(f"无法解析当前仓库 origin：{origin!r}")
        if origin_endpoint != configured_endpoint:
            origin_display = f"{origin_endpoint[0]}://{origin_endpoint[1]}:{origin_endpoint[2]}"
            raise RuntimeError(
                "当前仓库 origin 不属于配置的自托管 GitLab 实例："
                f"origin={origin_display}，"
                f"{_BASE_URL_ENV}={base_url}"
            )
        return GitlabTarget(
            base_url=base_url,
            project_path=_strip_git_suffix(parsed_origin.path),
        )

    if origin.startswith("ssh://"):
        parsed_origin = urlsplit(origin)
        origin_host = str(parsed_origin.hostname or "").lower().rstrip(".")
        if not origin_host or not parsed_origin.path:
            raise RuntimeError(f"无法解析当前仓库 origin：{origin!r}")
        if origin_host != configured_host:
            raise RuntimeError(
                "当前仓库 origin 主机与配置的自托管 GitLab 实例不一致："
                f"origin={origin_host}，{_BASE_URL_ENV}={configured_host}"
            )
        return GitlabTarget(
            base_url=base_url,
            project_path=_strip_git_suffix(parsed_origin.path),
        )

    ssh_match = re.match(r"^(?:[^@]+@)?(?P<host>[^:]+):(?P<path>.+)$", origin)
    if ssh_match:
        origin_host = ssh_match.group("host").lower().rstrip(".")
        if origin_host != configured_host:
            raise RuntimeError(
                "当前仓库 origin 主机与配置的自托管 GitLab 实例不一致："
                f"origin={origin_host}，{_BASE_URL_ENV}={configured_host}"
            )
        return GitlabTarget(
            base_url=base_url,
            project_path=_strip_git_suffix(ssh_match.group("path")),
        )

    raise RuntimeError(
        f"不支持当前仓库 origin 格式：{origin!r}；gitlab-issue 仅适用于当前自托管 GitLab 仓库"
    )


def _load_token() -> str:
    token = os.getenv(_TOKEN_ENV)
    if isinstance(token, str) and token.strip():
        return token.strip()
    raise RuntimeError(
        "GitLab token not configured. The script has already checked environment variables "
        "and the repo .env file. Please provide or export: "
        + _TOKEN_ENV
        + " (token content will not be printed)."
    )


def _project_api_path(project_path: str) -> str:
    return quote(project_path, safe="")


def _request(
    *,
    method: str,
    url: str,
    token: str,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> requests.Response:
    if requests is None:
        raise RuntimeError("缺少 Python 依赖 requests")
    resp = requests.request(
        method=method,
        url=url,
        headers={"PRIVATE-TOKEN": token},
        params=params,
        data=data,
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp


def _response_json(resp: requests.Response) -> Any:
    if not resp.content:
        return None
    return resp.json()


def _gitlab_project_id(*, base_url: str, token: str, project_path: str) -> int:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{_project_api_path(project_path)}"
    resp = _request(method="GET", url=url, token=token)
    data = _response_json(resp) or {}
    return int(data["id"])


def list_project_labels(
    *,
    base_url: str,
    token: str,
    project_id: int,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/labels"
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        resp = _request(
            method="GET",
            url=url,
            token=token,
            params={
                "page": page,
                "per_page": per_page,
            },
        )
        data = _response_json(resp) or []
        items.extend([dict(item) for item in data])
        next_page = (resp.headers.get("X-Next-Page") or "").strip()
        if not next_page:
            return items
        page = int(next_page)


def _labels_payload(labels: list[str] | None) -> str | None:
    if not labels:
        return None
    return ",".join(labels)


def create_issue(
    *,
    base_url: str,
    token: str,
    project_id: int,
    title: str,
    description: str,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/issues"
    data: dict[str, Any] = {"title": title, "description": description}
    labels_payload = _labels_payload(labels)
    if isinstance(labels_payload, str) and labels_payload:
        data["labels"] = labels_payload
    resp = _request(
        method="POST",
        url=url,
        token=token,
        data=data,
    )
    return dict(_response_json(resp) or {})


def get_issue(*, base_url: str, token: str, project_id: int, iid: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/issues/{int(iid)}"
    resp = _request(method="GET", url=url, token=token)
    return dict(_response_json(resp) or {})


def update_issue(
    *,
    base_url: str,
    token: str,
    project_id: int,
    iid: int,
    title: str | None = None,
    description: str | None = None,
    state_event: str | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if isinstance(title, str) and title.strip():
        data["title"] = title.strip()
    if isinstance(description, str):
        data["description"] = description
    if isinstance(state_event, str) and state_event.strip():
        data["state_event"] = state_event.strip()
    labels_payload = _labels_payload(labels)
    if isinstance(labels_payload, str) and labels_payload:
        data["labels"] = labels_payload
    if not data:
        raise RuntimeError("update 至少需要传一个变更项：--title / --body / --body-file / --state-event / --labels")

    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/issues/{int(iid)}"
    resp = _request(method="PUT", url=url, token=token, data=data)
    return dict(_response_json(resp) or {})


def delete_issue(*, base_url: str, token: str, project_id: int, iid: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/issues/{int(iid)}"
    try:
        _request(method="DELETE", url=url, token=token)
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in {404, 405}:
            raise RuntimeError("当前 GitLab 实例可能尚不支持删除 issue API，或当前用户无删除权限。") from exc
        raise
    return {"deleted": True, "iid": int(iid)}


def create_issue_note(*, base_url: str, token: str, project_id: int, iid: int, body: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/issues/{int(iid)}/notes"
    resp = _request(method="POST", url=url, token=token, data={"body": body})
    return dict(_response_json(resp) or {})


def delete_issue_note(*, base_url: str, token: str, project_id: int, iid: int, note_id: int) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/issues/{int(iid)}/notes/{int(note_id)}"
    _request(method="DELETE", url=url, token=token)
    return {"deleted": True, "iid": int(iid), "note_id": int(note_id)}


def list_issue_notes(
    *,
    base_url: str,
    token: str,
    project_id: int,
    iid: int,
    per_page: int = 100,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/issues/{int(iid)}/notes"
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        resp = _request(
            method="GET",
            url=url,
            token=token,
            params={
                "page": page,
                "per_page": per_page,
                "sort": "asc",
                "order_by": "created_at",
            },
        )
        data = _response_json(resp) or []
        batch = [dict(item) for item in data]
        items.extend(batch)
        if max_items is not None and len(items) >= max_items:
            return items[:max_items]
        next_page = (resp.headers.get("X-Next-Page") or "").strip()
        if not next_page:
            return items
        page = int(next_page)


def list_project_issues(
    *,
    base_url: str,
    token: str,
    project_id: int,
    state: str,
    search: str | None,
    labels: str | None,
    per_page: int = 100,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/issues"
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
            "state": state,
            "scope": "all",
            "order_by": "created_at",
            "sort": "desc",
        }
        if isinstance(search, str) and search.strip():
            params["search"] = search.strip()
        if isinstance(labels, str) and labels.strip():
            params["labels"] = labels.strip()

        resp = _request(method="GET", url=url, token=token, params=params)
        data = _response_json(resp) or []
        batch = [dict(item) for item in data]
        items.extend(batch)
        if max_items is not None and len(items) >= max_items:
            return items[:max_items]
        next_page = (resp.headers.get("X-Next-Page") or "").strip()
        if not next_page:
            return items
        page = int(next_page)


def _load_body(*, body: str | None, body_file: Path | None, allow_empty: bool = False) -> str | None:
    if isinstance(body, str):
        if body or allow_empty:
            return body
        raise RuntimeError("--body 不能为空；若需清空 description，请使用 --body \"\"")

    if body_file is None:
        return None
    if not body_file.exists():
        raise RuntimeError(f"body-file not found: {body_file}")
    return body_file.read_text(encoding="utf-8")


def _parse_labels_arg(raw: str | None) -> list[str] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    seen: set[str] = set()
    labels: list[str] = []
    for part in raw.split(","):
        label = part.strip()
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels or None


def _assert_labels_exist(
    *,
    base_url: str,
    token: str,
    project_id: int,
    labels: list[str] | None,
) -> list[str] | None:
    if not labels:
        return None
    existing = {
        str(item.get("name") or "").strip()
        for item in list_project_labels(base_url=base_url, token=token, project_id=project_id)
    }
    missing = [label for label in labels if label not in existing]
    if missing:
        raise RuntimeError(
            "These labels do not exist in the current GitLab project, "
            "and the CLI refuses to create new labels implicitly: "
            + ", ".join(missing)
        )
    return labels


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _resolve_target() -> GitlabTarget:
    return _origin_target(base_url=_load_base_url())


def _build_common_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Manage issues for the current self-hosted GitLab repository."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _build_common_parser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="创建新 issue")
    create_parser.add_argument("--title", required=True, help="Issue 标题")
    create_parser.add_argument("--labels", help="Issue labels，逗号分隔；仅允许使用项目内已有 labels")
    create_body_group = create_parser.add_mutually_exclusive_group(required=True)
    create_body_group.add_argument("--body", help="Issue description 文本")
    create_body_group.add_argument("--body-file", type=Path, help="Issue description Markdown 文件")

    read_parser = subparsers.add_parser("read", help="读取单个 issue")
    read_parser.add_argument("--iid", type=int, required=True, help="Issue IID")
    read_parser.add_argument("--notes", action="store_true", help="同时拉取 issue 评论")
    read_parser.add_argument("--notes-limit", type=int, default=100, help="评论最大返回条数（默认 100）")

    list_parser = subparsers.add_parser("list", help="列出当前项目 issue")
    list_parser.add_argument("--state", choices=("opened", "closed", "all"), default="all", help="Issue 状态过滤")
    list_parser.add_argument("--search", help="按标题/description 搜索")
    list_parser.add_argument("--labels", help="按 GitLab labels 过滤，逗号分隔")
    list_parser.add_argument("--limit", type=int, help="最多返回多少条；默认拉取全部分页")

    update_parser = subparsers.add_parser("update", help="更新 issue 标题/description/状态")
    update_parser.add_argument("--iid", type=int, required=True, help="Issue IID")
    update_parser.add_argument("--title", help="新的 issue 标题")
    update_parser.add_argument("--labels", help="新的 issue labels，逗号分隔；仅允许使用项目内已有 labels")
    update_body_group = update_parser.add_mutually_exclusive_group()
    update_body_group.add_argument("--body", help="新的 issue description 文本；传空串可清空")
    update_body_group.add_argument("--body-file", type=Path, help="新的 issue description Markdown 文件")
    update_parser.add_argument("--append", action="store_true", help="把新内容追加到既有 description 后")
    update_parser.add_argument(
        "--state-event",
        choices=("close", "reopen"),
        help="状态变更；close 表示关闭，reopen 表示重开",
    )

    comment_parser = subparsers.add_parser("comment", help="回复 issue")
    comment_parser.add_argument("--iid", type=int, required=True, help="Issue IID")
    comment_body_group = comment_parser.add_mutually_exclusive_group(required=True)
    comment_body_group.add_argument("--body", help="评论文本")
    comment_body_group.add_argument("--body-file", type=Path, help="评论 Markdown 文件")

    delete_note_parser = subparsers.add_parser("delete-note", help="删除 issue 评论")
    delete_note_parser.add_argument("--iid", type=int, required=True, help="Issue IID")
    delete_note_parser.add_argument("--note-id", type=int, required=True, help="评论 note ID")

    delete_parser = subparsers.add_parser("delete", help="删除 issue")
    delete_parser.add_argument("--iid", type=int, required=True, help="Issue IID")
    delete_parser.add_argument("--yes", action="store_true", help="确认执行删除")

    return parser


def run_cli(args: argparse.Namespace) -> int:
    _ensure_runtime_dependencies()
    _load_repo_dotenv()
    target = _resolve_target()
    token = _load_token()
    project_id = _gitlab_project_id(base_url=target.base_url, token=token, project_path=target.project_path)

    if args.command == "create":
        description = _load_body(body=args.body, body_file=args.body_file)
        labels = _assert_labels_exist(
            base_url=target.base_url,
            token=token,
            project_id=project_id,
            labels=_parse_labels_arg(args.labels),
        )
        issue = create_issue(
            base_url=target.base_url,
            token=token,
            project_id=project_id,
            title=str(args.title).strip(),
            description=str(description),
            labels=labels,
        )
        _print_json(issue)
        return 0

    if args.command == "read":
        issue = get_issue(base_url=target.base_url, token=token, project_id=project_id, iid=args.iid)
        if args.notes:
            notes = list_issue_notes(
                base_url=target.base_url,
                token=token,
                project_id=project_id,
                iid=args.iid,
                max_items=args.notes_limit,
            )
            _print_json({"issue": issue, "notes": notes})
        else:
            _print_json(issue)
        return 0

    if args.command == "list":
        issues = list_project_issues(
            base_url=target.base_url,
            token=token,
            project_id=project_id,
            state=args.state,
            search=args.search,
            labels=args.labels,
            max_items=args.limit,
        )
        _print_json({"count": len(issues), "issues": issues})
        return 0

    if args.command == "update":
        new_desc = _load_body(body=args.body, body_file=args.body_file, allow_empty=True)
        description: str | None = new_desc
        if args.append:
            if new_desc is None:
                raise RuntimeError("--append 只能与 --body 或 --body-file 一起使用")
            current = get_issue(base_url=target.base_url, token=token, project_id=project_id, iid=args.iid)
            current_desc = str(current.get("description") or "")
            description = (current_desc.rstrip() + "\n\n" + new_desc.lstrip()).strip() + "\n"
        labels = _assert_labels_exist(
            base_url=target.base_url,
            token=token,
            project_id=project_id,
            labels=_parse_labels_arg(args.labels),
        )
        issue = update_issue(
            base_url=target.base_url,
            token=token,
            project_id=project_id,
            iid=args.iid,
            title=args.title,
            description=description,
            state_event=args.state_event,
            labels=labels,
        )
        _print_json(issue)
        return 0

    if args.command == "comment":
        body = _load_body(body=args.body, body_file=args.body_file)
        note = create_issue_note(
            base_url=target.base_url,
            token=token,
            project_id=project_id,
            iid=args.iid,
            body=str(body),
        )
        _print_json(note)
        return 0

    if args.command == "delete-note":
        result = delete_issue_note(
            base_url=target.base_url,
            token=token,
            project_id=project_id,
            iid=args.iid,
            note_id=args.note_id,
        )
        _print_json(result)
        return 0

    if args.command == "delete":
        if not args.yes:
            raise RuntimeError("删除 issue 需要显式传 --yes")
        result = delete_issue(base_url=target.base_url, token=token, project_id=project_id, iid=args.iid)
        _print_json(result)
        return 0

    raise RuntimeError(f"Unsupported command: {args.command!r}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_cli(args)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if requests is not None and isinstance(exc, requests.RequestException):
            print(f"GitLab API 请求失败：{exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
