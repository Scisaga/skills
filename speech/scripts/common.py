import importlib
import logging
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent


def configure_logging(*, quiet: bool, verbose: bool) -> None:
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def get_env_candidates(env_file: str | None) -> list[Path]:
    if env_file:
        return [Path(env_file)]
    return [
        Path.cwd() / ".env",
        SKILL_ROOT / ".env",
        SCRIPTS_DIR / ".env",
    ]


def load_env(*, env_file: str | None, logger: logging.Logger) -> Path | None:
    candidates = get_env_candidates(env_file)

    try:
        from dotenv import load_dotenv
    except ImportError:
        existing = [candidate for candidate in candidates if candidate.exists()]
        if env_file or existing:
            logger.warning(
                "检测到 .env 配置，但缺少 `python-dotenv`，无法自动加载。请先安装 `python-dotenv` 或手动导出环境变量。"
            )
        return None

    for candidate in candidates:
        if not candidate.exists():
            continue
        load_dotenv(candidate, override=False)
        logger.debug("已加载环境变量文件: %s", candidate)
        return candidate

    if env_file:
        logger.warning("指定的 .env 文件不存在: %s", env_file)
    return None


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
