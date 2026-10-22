import importlib
import json
import logging
import os
import tempfile
from pathlib import Path

SKILL_ROOT = Path(os.path.abspath(__file__)).parents[1]
SCRIPTS_DIR = Path(os.path.abspath(__file__)).parent


def configure_logging(*, quiet: bool, verbose: bool) -> None:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def get_env_candidates(env_file: str | None) -> list[Path]:
    return ([Path(env_file).expanduser()] if env_file else []) + [
        Path.cwd() / ".env",
        SKILL_ROOT / ".env",
        SCRIPTS_DIR / ".env",
    ]


def load_env(*, env_file: str | None, logger: logging.Logger) -> Path | None:
    candidates = get_env_candidates(env_file)
    if env_file and not candidates[0].is_file():
        raise RuntimeError(f"指定的 .env 文件不存在: {env_file}")

    try:
        from dotenv import load_dotenv
    except ImportError:
        existing = [candidate for candidate in candidates if candidate.exists()]
        if env_file or existing:
            raise RuntimeError(
                "检测到 .env 配置，但缺少 python-dotenv；安装：python -m pip install python-dotenv"
            )
        return None

    loaded = None
    seen = set()
    for candidate in candidates:
        candidate = candidate.expanduser().absolute()
        if not candidate.is_file() or candidate in seen:
            continue
        seen.add(candidate)
        load_dotenv(candidate, override=False, encoding="utf-8-sig")
        logger.debug("已加载环境变量文件: %s", candidate)
        loaded = loaded or candidate

    return loaded


def write_object(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".speech-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure_python_modules(
    required_modules: dict[str, str],
    *,
    logger: logging.Logger,
) -> None:
    missing_packages: list[str] = []

    for module_name, package_name in required_modules.items():
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing_packages.append(package_name)

    if not missing_packages:
        return

    deduped = list(dict.fromkeys(missing_packages))
    logger.error("缺少 Python 依赖: %s", ", ".join(deduped))
    raise RuntimeError(f"请先执行 `python3 -m pip install {' '.join(deduped)}`")
