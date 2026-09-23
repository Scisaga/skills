from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import quote, unquote, urlencode

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


BASE_URLS = {
    ("gandi", "production"): "https://api.gandi.net",
    ("gandi", "sandbox"): "https://api.sandbox.gandi.net",
    ("dynadot", "production"): "https://api.dynadot.com",
    ("dynadot", "sandbox"): "https://api-sandbox.dynadot.com",
}
PATH_PREFIXES = {
    "gandi": "/v5/",
    "dynadot": "/restful/v2/",
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_METHODS = SAFE_METHODS | {"POST", "PUT", "PATCH", "DELETE"}
HARD_SECRET_KEY = re.compile(
    r"(^|_)(authorization|password|passwd|secret|signature|token|api_key)(_|$)",
    re.IGNORECASE,
)
SOFT_SECRET_KEYS = {
    "auth_code",
    "authinfo",
    "authorization_code",
    "epp_code",
    "transfer_auth_code",
    "transferauthorizationcode",
}
SAFE_RESPONSE_HEADERS = {
    "content-type",
    "location",
    "ratelimit-limit",
    "ratelimit-remaining",
    "ratelimit-reset",
    "retry-after",
    "total-count",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-request-id",
}


@dataclass(frozen=True)
class RequestSpec:
    provider: str
    environment: str
    method: str
    path: str
    query: tuple[tuple[str, str], ...]
    path_and_query: str
    body_value: Any | None
    body_text: str
    base_url: str
    url: str


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _print_json(value: Any, *, stream: Any | None = None) -> None:
    print(_json_dump(value), file=stream if stream is not None else sys.stdout)


def ensure_runtime_dependencies() -> None:
    missing: list[str] = []
    if requests is None:
        missing.append("requests")
    if load_dotenv is None:
        missing.append("python-dotenv")
    if missing:
        raise RuntimeError(
            "缺少 Python 依赖："
            + ", ".join(missing)
            + "。请先执行 skills/domain-manager/scripts/run.sh bootstrap"
        )


def dotenv_candidates() -> list[Path]:
    script_dir = Path(__file__).resolve().parent
    skill_root = script_dir.parent
    candidates = [Path.cwd() / ".env", skill_root / ".env", script_dir / ".env"]
    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(candidate)
    return result


def load_environment() -> list[str]:
    ensure_runtime_dependencies()
    loaded: list[str] = []
    assert load_dotenv is not None
    for env_path in dotenv_candidates():
        if env_path.is_file():
            load_dotenv(env_path, override=False)
            loaded.append(str(env_path.resolve()))
    return loaded


def _configured(name: str) -> bool:
    value = os.getenv(name)
    return isinstance(value, str) and bool(value.strip())


def run_doctor() -> int:
    loaded = load_environment()
    gandi_ready = _configured("GANDI_PAT_TOKEN")
    dynadot_key = _configured("DYNADOT_API_KEY")
    dynadot_secret = _configured("DYNADOT_API_SECRET")
    result = {
        "ok": gandi_ready or (dynadot_key and dynadot_secret),
        "network_checked": False,
        "dotenv_files": loaded,
        "providers": {
            "gandi": {"ready": gandi_ready, "GANDI_PAT_TOKEN": gandi_ready},
            "dynadot": {
                "ready": dynadot_key and dynadot_secret,
                "DYNADOT_API_KEY": dynadot_key,
                "DYNADOT_API_SECRET": dynadot_secret,
            },
        },
    }
    _print_json(result)
    return 0 if result["ok"] else 1


def validate_path(provider: str, path: str) -> str:
    if not path or not path.startswith("/") or path.startswith("//"):
        raise ValueError("PATH 必须以单个 / 开头")
    if any(char in path for char in ("?", "#", "\\")) or "://" in path:
        raise ValueError("PATH 不得包含 host、query、fragment 或反斜杠；query 请使用 --query")
    if any(ord(char) < 32 or char.isspace() for char in path):
        raise ValueError("PATH 不得包含空白或控制字符")
    try:
        path.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("PATH 必须使用 ASCII；国际化域名请使用 Punycode") from exc
    decoded_segments = unquote(path).split("/")
    if any(segment in {".", ".."} for segment in decoded_segments):
        raise ValueError("PATH 不得包含路径穿越片段")
    prefix = PATH_PREFIXES[provider]
    if not path.startswith(prefix):
        raise ValueError(f"{provider} PATH 必须以 {prefix} 开头")
    return path


def parse_query(items: Sequence[str]) -> tuple[tuple[str, str], ...]:
    parsed: list[tuple[str, str]] = []
    for item in items:
        if "=" not in item:
            raise ValueError(f"无效 --query：{item!r}；必须使用 KEY=VALUE")
        key, value = item.split("=", 1)
        if not key or any(ord(char) < 32 for char in key):
            raise ValueError("query key 不能为空或包含控制字符")
        parsed.append((key, value))
    return tuple(parsed)


def parse_body(body: str | None, body_file: str | None) -> tuple[Any | None, str]:
    if body is None and body_file is None:
        return None, ""
    if body_file == "-":
        raw = sys.stdin.read()
    elif body_file is not None:
        raw = Path(body_file).read_text(encoding="utf-8")
    else:
        raw = body or ""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"请求体不是有效 JSON：{exc}") from exc
    canonical = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return value, canonical


def build_request_spec(
    provider: str,
    environment: str,
    method: str,
    path: str,
    query: Sequence[tuple[str, str]],
    body_value: Any | None,
    body_text: str,
) -> RequestSpec:
    if provider not in PATH_PREFIXES:
        raise ValueError(f"不支持的供应商：{provider}")
    normalized_method = method.upper()
    if normalized_method not in ALLOWED_METHODS:
        raise ValueError(f"不支持的 HTTP 方法：{method}")
    normalized_path = validate_path(provider, path)
    if normalized_method in SAFE_METHODS and body_text:
        raise ValueError(f"{normalized_method} 请求不得携带 body")
    query_string = urlencode(list(query), doseq=False, quote_via=quote)
    path_and_query = normalized_path + (f"?{query_string}" if query_string else "")
    base_url = BASE_URLS[(provider, environment)]
    return RequestSpec(
        provider=provider,
        environment=environment,
        method=normalized_method,
        path=normalized_path,
        query=tuple(query),
        path_and_query=path_and_query,
        body_value=body_value,
        body_text=body_text,
        base_url=base_url,
        url=base_url + path_and_query,
    )


def plan_id(spec: RequestSpec) -> str:
    canonical = json.dumps(
        {
            "provider": spec.provider,
            "environment": spec.environment,
            "method": spec.method,
            "path_and_query": spec.path_and_query,
            "body": spec.body_text,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")


def _must_redact_key(key: Any, *, show_sensitive: bool) -> bool:
    normalized = _normalized_key(key)
    if HARD_SECRET_KEY.search(normalized):
        return True
    return not show_sensitive and normalized in SOFT_SECRET_KEYS


def redact_data(value: Any, *, show_sensitive: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "<redacted>"
                if _must_redact_key(key, show_sensitive=show_sensitive)
                else redact_data(item, show_sensitive=show_sensitive)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_data(item, show_sensitive=show_sensitive) for item in value]
    return value


def redact_path_and_query(spec: RequestSpec) -> str:
    if not spec.query:
        return spec.path
    redacted_query: list[tuple[str, str]] = []
    for key, value in spec.query:
        replacement = "<redacted>" if _must_redact_key(key, show_sensitive=False) else value
        redacted_query.append((key, replacement))
    return spec.path + "?" + urlencode(redacted_query, doseq=False, quote_via=quote)


def request_summary(spec: RequestSpec) -> dict[str, Any]:
    return {
        "provider": spec.provider,
        "environment": spec.environment,
        "method": spec.method,
        "path_and_query": redact_path_and_query(spec),
        "body": redact_data(spec.body_value) if spec.body_value is not None else None,
    }


def create_dynadot_signature(
    api_key: str,
    api_secret: str,
    full_path_and_query: str,
    request_id: str,
    request_body: str = "",
) -> str:
    string_to_sign = "\n".join((api_key, full_path_and_query, request_id, request_body))
    digest = hmac.new(
        api_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"未配置 {name}；请写入环境变量或受支持的 .env")
    return value.strip()


def build_auth_headers(spec: RequestSpec) -> tuple[dict[str, str], list[str]]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "domain-manager-skill/1.0",
    }
    secrets: list[str] = []
    if spec.body_text:
        headers["Content-Type"] = "application/json"
    if spec.provider == "gandi":
        token = _require_env("GANDI_PAT_TOKEN")
        headers["Authorization"] = f"Bearer {token}"
        secrets.append(token)
    else:
        api_key = _require_env("DYNADOT_API_KEY")
        api_secret = _require_env("DYNADOT_API_SECRET")
        request_id = str(uuid.uuid4())
        signature = create_dynadot_signature(
            api_key,
            api_secret,
            spec.path_and_query,
            request_id,
            spec.body_text,
        )
        headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "X-Request-ID": request_id,
                "X-Signature": signature,
            }
        )
        secrets.extend((api_key, api_secret, signature))
    return headers, secrets


def scrub_text(text: str, secrets: Iterable[str]) -> str:
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, "<redacted>")
    return result


def _safe_response_headers(headers: Any, secrets: Iterable[str]) -> dict[str, str]:
    return {
        key: scrub_text(value, secrets)
        for key, value in headers.items()
        if key.lower() in SAFE_RESPONSE_HEADERS
    }


def _response_data(response: Any, secrets: Iterable[str], show_sensitive: bool) -> Any:
    try:
        parsed = response.json()
    except ValueError:
        return scrub_text(response.text, secrets)
    redacted = redact_data(parsed, show_sensitive=show_sensitive)
    serialized = scrub_text(json.dumps(redacted, ensure_ascii=False), secrets)
    return json.loads(serialized)


def execute_request(spec: RequestSpec, timeout: float, show_sensitive: bool) -> int:
    load_environment()
    headers, secrets = build_auth_headers(spec)
    assert requests is not None
    try:
        response = requests.request(
            spec.method,
            spec.url,
            headers=headers,
            data=spec.body_text.encode("utf-8") if spec.body_text else None,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        _print_json(
            {
                "ok": False,
                "provider": spec.provider,
                "environment": spec.environment,
                "error": scrub_text(str(exc), secrets),
            },
            stream=sys.stderr,
        )
        return 1

    result = {
        "ok": 200 <= response.status_code < 300,
        "provider": spec.provider,
        "environment": spec.environment,
        "status": response.status_code,
        "accepted_async": response.status_code == 202,
        "headers": _safe_response_headers(response.headers, secrets),
        "data": _response_data(response, secrets, show_sensitive),
    }
    _print_json(result)
    return 0 if result["ok"] else 1


def run_request(args: argparse.Namespace) -> int:
    query = parse_query(args.query)
    body_value, body_text = parse_body(args.body, args.body_file)
    environment = "sandbox" if args.sandbox else "production"
    spec = build_request_spec(
        args.provider,
        environment,
        args.method,
        args.path,
        query,
        body_value,
        body_text,
    )
    confirmation = plan_id(spec)
    is_mutation = spec.method not in SAFE_METHODS
    should_plan = args.plan or (is_mutation and not args.apply)

    if should_plan:
        _print_json(
            {
                "ok": True,
                "mode": "plan",
                "will_send": False,
                "confirmation": confirmation,
                "request": request_summary(spec),
            }
        )
        return 0

    if is_mutation:
        if not args.confirm:
            raise RuntimeError(
                "写请求必须传 --confirm <confirmation>；请先省略 --apply 生成计划"
            )
        if not hmac.compare_digest(args.confirm, confirmation):
            raise RuntimeError(
                "确认码与当前请求不匹配；请求内容可能已变化，请重新生成并复核计划"
            )

    return execute_request(spec, args.timeout, args.show_sensitive)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="安全发送 Gandi v5 与 Dynadot RESTful v2 域名管理请求"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="检查依赖和凭据是否存在，不联网")

    request_parser = subparsers.add_parser("request", help="构造、计划或执行 API 请求")
    request_parser.add_argument("provider", choices=("gandi", "dynadot"))
    request_parser.add_argument("method", help="GET、POST、PUT、PATCH、DELETE、HEAD 或 OPTIONS")
    request_parser.add_argument("path", help="供应商根地址下的 API 路径")
    request_parser.add_argument(
        "--query",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="查询参数，可重复",
    )
    body_group = request_parser.add_mutually_exclusive_group()
    body_group.add_argument("--body", help="JSON 请求体")
    body_group.add_argument("--body-file", help="JSON 文件路径，- 表示 stdin")
    request_parser.add_argument("--sandbox", action="store_true", help="使用供应商沙箱")
    request_parser.add_argument("--plan", action="store_true", help="只输出计划，不发送请求")
    request_parser.add_argument("--apply", action="store_true", help="允许执行写请求")
    request_parser.add_argument("--confirm", help="计划输出的确认码")
    request_parser.add_argument(
        "--show-sensitive",
        action="store_true",
        help="显示业务敏感响应字段；本地 API 凭据仍会遮蔽",
    )
    request_parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="请求超时秒数，默认 30",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return run_doctor()
        if not 1 <= args.timeout <= 300:
            raise ValueError("--timeout 必须在 1 到 300 秒之间")
        return run_request(args)
    except (OSError, RuntimeError, ValueError) as exc:
        _print_json({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
