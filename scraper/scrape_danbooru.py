#pyright: standard
import _pre_init
import argparse
import os
import shutil
import subprocess
from pathlib import Path


REQUEST_TIMEOUT_SECONDS = 30


class CliArgs(argparse.Namespace):
    url: str
    output: str | None
    timeout: int
    headless: bool
    profile_dir: str | None


def resolve_node_path() -> str:
    candidates = [
        os.environ.get("PLAYWRIGHT_NODE_PATH"),
        str(Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "bin" / "node.exe"),
        shutil.which("node"),
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate

    raise RuntimeError("Failed to find Node.js. Set PLAYWRIGHT_NODE_PATH or install Node.js.")


def resolve_playwright_package_dir() -> Path:
    env_node_modules = os.environ.get("PLAYWRIGHT_NODE_MODULES")
    candidates = [
        Path(env_node_modules) / "playwright" if env_node_modules else None,
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "node" / "node_modules" / "playwright",
        Path.cwd() / "node_modules" / "playwright",
    ]

    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate

    raise RuntimeError(
        "Failed to find Playwright package. Set PLAYWRIGHT_NODE_MODULES or install Playwright for Node.js."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Danbooru 图片抓取脚本 (Playwright 浏览器版)")
    parser.add_argument("url", type=str, help="目标网页 URL")
    parser.add_argument("-o", "--output", type=str, default=None, help="图片保存目录 (默认: .danbooru)")
    parser.add_argument(
        "--timeout",
        type=int,
        default=REQUEST_TIMEOUT_SECONDS,
        help=f"请求超时秒数，0 表示不超时 (默认: {REQUEST_TIMEOUT_SECONDS})",
    )
    parser.add_argument("--headless", action="store_true", help="以无头模式运行浏览器")
    parser.add_argument(
        "--profile-dir",
        type=str,
        default=None,
        help="浏览器用户数据目录 (默认: scraper/.danbooru_profile)",
    )
    args = parser.parse_args(namespace=CliArgs())

    if args.timeout < 0:
        raise ValueError("--timeout must be greater than or equal to 0.")

    output_dir = Path(args.output) if args.output else Path(__file__).parent / ".danbooru"
    output_dir.mkdir(parents=True, exist_ok=True)

    profile_dir = Path(args.profile_dir) if args.profile_dir else Path(__file__).parent / ".danbooru_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    node_path = resolve_node_path()
    playwright_package_dir = resolve_playwright_package_dir()
    browser_script_path = Path(__file__).with_name("scrape_danbooru_browser.cjs")

    command = [
        node_path,
        str(browser_script_path),
        "--url",
        args.url,
        "--output",
        str(output_dir),
        "--timeout",
        str(args.timeout),
        "--profile-dir",
        str(profile_dir),
        "--playwright-package-dir",
        str(playwright_package_dir),
    ]
    if args.headless:
        command.append("--headless")

    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
