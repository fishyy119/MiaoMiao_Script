# pyright: standard
import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Set, cast
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
from rich.console import Console
from tqdm import tqdm

REQUEST_DELAY_MS = 500
POSTS_PER_PAGE = 200
MAX_FILENAME_LENGTH = 64
REMOVED_POST_TEXT = "This page has been removed because of a takedown request."
GOLD_ONLY_TEXT = "You need a gold account to see this image."
console = Console(file=sys.stderr)


@dataclass(slots=True)
class Args:
    url: str
    output: Path
    timeout_ms: int
    headless: bool
    profile_dir: Path

    @classmethod
    def from_ns(cls, namespace: argparse.Namespace) -> "Args":
        timeout_seconds = namespace.timeout
        if timeout_seconds < 0:
            raise ValueError("--timeout must be greater than or equal to 0.")

        timeout_ms = 0 if timeout_seconds == 0 else timeout_seconds * 1000
        base_dir = Path(__file__).parent
        output_dir = Path(namespace.output) if namespace.output else base_dir / ".danbooru"
        profile_dir = Path(namespace.profile_dir) if namespace.profile_dir else base_dir / ".danbooru_profile"

        return cls(
            url=namespace.url,
            output=output_dir,
            timeout_ms=timeout_ms,
            headless=namespace.headless,
            profile_dir=profile_dir,
        )


# 在主函数中统一assert验证过，这里不标 Optional 是因为类型系统局限性
args: Args = cast(Args, None)
existing_file_hashes: Set[str] = cast(Set[str], None)
download_page: Page = cast(Page, None)


def load_args() -> None:
    global args
    parser = argparse.ArgumentParser(description="Danbooru 资源抓取脚本 (Playwright Python API)")
    parser.add_argument("url", type=str, help="目标网页 URL")
    parser.add_argument("-o", "--output", type=str, default=None, help="资源保存目录 (默认: .danbooru)")
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help=f"请求超时秒数，0 表示不超时 (默认: 30)",
    )
    parser.add_argument("--headless", action="store_true", help="以无头模式运行浏览器")
    parser.add_argument(
        "--profile-dir",
        type=str,
        default=None,
        help="浏览器用户数据目录 (默认: scraper/.danbooru_profile)",
    )
    args = Args.from_ns(parser.parse_args())


def log(message: str) -> None:
    with tqdm.external_write_mode(file=sys.stderr):
        console.print(message)


class SkipPostError(RuntimeError):
    pass


def build_api_query_params() -> list[tuple[str, str]]:
    parsed = urlsplit(args.url)
    cleaned: list[tuple[str, str]] = []

    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_value = " ".join(value.strip().split()) if key == "tags" else value.strip()
        if normalized_value:
            cleaned.append((key, normalized_value))

    return cleaned


def build_posts_api_url(page: int) -> str:
    parsed = urlsplit(args.url)
    query_params = [(key, value) for key, value in build_api_query_params() if key != "z"]
    query_params = [(key, value) for key, value in query_params if key not in {"page", "limit"}]
    query_params.append(("page", str(page)))
    query_params.append(("limit", str(POSTS_PER_PAGE)))
    return urlunsplit((parsed.scheme, parsed.netloc, "/posts.json", urlencode(query_params), ""))


def build_counts_api_url() -> str:
    parsed = urlsplit(args.url)
    query_params = [(key, value) for key, value in build_api_query_params() if key not in {"z", "page", "limit"}]
    return urlunsplit((parsed.scheme, parsed.netloc, "/counts/posts.json", urlencode(query_params), ""))


def build_post_url(post_id: str) -> str:
    return urlunsplit(urlsplit(args.url)._replace(path=f"/posts/{post_id}", query="", fragment=""))


def get_post_id(post: object) -> str | None:
    if not isinstance(post, Mapping):
        return None

    post_id = post.get("id")
    if isinstance(post_id, int):
        return str(post_id)

    if isinstance(post_id, str) and post_id.isdigit():
        return post_id

    return None


def get_post_hash(post: object) -> str | None:
    if not isinstance(post, Mapping):
        return None

    candidates = [post.get("md5")]
    media_asset = post.get("media_asset")
    if isinstance(media_asset, Mapping):
        candidates.append(media_asset.get("md5"))

    for candidate in candidates:
        if isinstance(candidate, str) and re.fullmatch(r"[a-f0-9]{32}", candidate, re.IGNORECASE):
            return candidate.lower()

    return None


def resolve_download_filename(download_url: str, download_attribute: str | None) -> str:
    res = ""
    if isinstance(download_attribute, str):
        res = candidate if (candidate := download_attribute.strip().replace("\\", "/").rsplit("/", 1)[-1]) else ""

    if len(res) == 0:
        parsed = urlsplit(download_url)
        filename = unquote(parsed.path).rsplit("/", 1)[-1]
        if not filename:
            raise RuntimeError(f"Invalid file URL: {download_url}")
        res = filename

    terms = res.rsplit(" - ", 1)
    if len(terms) == 2:
        res = f"{terms[0][:MAX_FILENAME_LENGTH - len(terms[1]) - 3]} - {terms[1]}"
    else:
        res = res[:MAX_FILENAME_LENGTH]

    return re.sub(r'[\\/:*?"<>|]', " ", res)


def extract_embedded_hash(filename: str) -> str | None:
    stem = Path(filename).stem
    separator_index = stem.rfind(" - ")
    if separator_index < 0:
        return None

    candidate = stem[separator_index + 3 :].strip()
    if not re.fullmatch(r"[a-f0-9]{32}", candidate, re.IGNORECASE):
        return None

    return candidate.lower()


def calculate_file_md5(file_path: Path) -> str:
    hasher = hashlib.md5()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def initialize_existing_file_hashes(output_dir: Path) -> None:
    global existing_file_hashes
    hashes: set[str] = set()

    for entry in output_dir.iterdir():
        if not entry.is_file():
            continue

        hash_value = extract_embedded_hash(entry.name) or calculate_file_md5(entry)
        if hash_value:
            hashes.add(hash_value)

    existing_file_hashes = hashes


def delay(ms: int) -> None:
    time.sleep(ms / 1000)


def get_error_message(error: BaseException) -> str:
    return str(error)


def is_challenge_page(page: Page) -> bool:
    title = page.title()
    if "Just a moment" in title:
        return True

    try:
        body_text = page.locator("body").inner_text()
    except Exception:
        body_text = ""
    return "Enable JavaScript and cookies to continue" in body_text


def get_non_downloadable_reason(page: Page) -> str | None:
    try:
        body_text = page.locator("body").inner_text()
    except Exception:
        return None

    if REMOVED_POST_TEXT in body_text:
        return "post removed by takedown request"
    if GOLD_ONLY_TEXT in body_text:
        return "post requires gold account"
    return None


def wait_for_challenge_clear(page: Page) -> None:
    if not is_challenge_page(page):
        return

    if args.headless:
        raise RuntimeError(
            "Cloudflare challenge detected in headless mode. Rerun without --headless and pass the challenge in the browser."
        )

    log(
        "[yellow]Cloudflare challenge detected.[/yellow] Complete it in the opened browser, then press Enter here to continue."
    )
    sys.stdin.readline()

    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except PlaywrightTimeoutError:
        pass

    if is_challenge_page(page):
        raise RuntimeError("Cloudflare challenge is still active after manual confirmation.")


def fetch_json_in_page(page: Page, target_url: str) -> Any:
    result = page.evaluate(
        """
        async ({ url, timeoutMs }) => {
          const controller = new AbortController();
          const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;

          try {
            const response = await fetch(url, { credentials: "include", signal: controller.signal });
            const text = await response.text();
            return {
              ok: response.ok,
              status: response.status,
              text,
              url: response.url,
              timedOut: false,
              fetchError: "",
            };
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            return {
              ok: false,
              status: 0,
              text: "",
              url,
              timedOut: timeoutMs > 0 && message.toLowerCase().includes("abort"),
              fetchError: message,
            };
          } finally {
            if (timer !== null) {
              clearTimeout(timer);
            }
          }
        }
        """,
        {"url": target_url, "timeoutMs": args.timeout_ms},
    )

    if not isinstance(result, Mapping):
        raise RuntimeError(f"Unexpected fetch result for {target_url}")

    if result.get("timedOut"):
        raise RuntimeError(f"Timed out fetching {target_url}")

    fetch_error = result.get("fetchError")
    if isinstance(fetch_error, str) and fetch_error:
        raise RuntimeError(f"Failed to fetch {target_url}: {fetch_error}")

    if not result.get("ok"):
        status = result.get("status")
        text = result.get("text")
        if status == 403 and isinstance(text, str) and "Just a moment" in text:
            raise RuntimeError(f"Cloudflare challenge for {target_url}")
        raise RuntimeError(f"HTTP {status} for {target_url}")

    text = result.get("text")
    if not isinstance(text, str):
        raise RuntimeError(f"Unexpected response body for {target_url}")

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        response_url = result.get("url")
        source_url = response_url if isinstance(response_url, str) and response_url else target_url
        raise RuntimeError(f"Failed to parse JSON from {source_url}") from error


def parse_total_posts(payload: Any) -> int:
    if isinstance(payload, int):
        return payload

    if not isinstance(payload, Mapping):
        raise RuntimeError(f"Unexpected counts payload type: {type(payload).__name__}")

    candidates: list[object] = [payload.get("posts"), payload.get("count"), payload.get("post_count")]
    counts = payload.get("counts")
    if isinstance(counts, Mapping):
        candidates.extend([counts.get("posts"), counts.get("count"), counts.get("post_count")])

    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate
        if isinstance(candidate, str) and candidate.isdigit():
            return int(candidate)

    raise RuntimeError(f"Failed to parse total posts from counts payload: {json.dumps(payload, ensure_ascii=False)}")


def fetch_posts(page: Page, page_number: int) -> list[Any]:
    url = build_posts_api_url(page_number)
    payload = fetch_json_in_page(page, url)
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected posts payload type for {url}")
    return payload


def prefetch_posts_pages(page: Page) -> list[list[Any]]:
    pages: list[list[Any]] = []

    page_number = 1
    while True:
        log(f"Prefetching page {page_number} to determine total pages...")
        posts = fetch_posts(page, page_number)
        if not posts:
            break

        pages.append(posts)
        if len(posts) < POSTS_PER_PAGE:
            break

        page_number += 1

    return pages


def fetch_total_pages(page: Page) -> tuple[int, int, list[list[Any]] | None]:
    counts_url = build_counts_api_url()

    try:
        payload = fetch_json_in_page(page, counts_url)
        total_posts = parse_total_posts(payload)
        log(f"[green]Total posts:[/green] {total_posts}")
        return max((total_posts + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE, 1), total_posts, None
    except Exception as error:
        message = get_error_message(error)
        if "Cloudflare challenge" not in message:
            raise

        log(f"[yellow]Counts endpoint blocked, fallback to paging posts:[/yellow] {counts_url}")
        cached_pages = prefetch_posts_pages(page)
        total_posts = sum(len(posts) for posts in cached_pages)
        log(f"[green]Total posts:[/green] {total_posts}")
        return max(len(cached_pages), 1), total_posts, cached_pages


def get_download_link() -> Locator:
    return download_page.get_by_role("link", name=re.compile(r"^Download$"))


def prepare_download(post_url: str) -> Path:
    download_page.goto(post_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
    wait_for_challenge_clear(download_page)
    non_downloadable_reason = get_non_downloadable_reason(download_page)
    if non_downloadable_reason:
        raise SkipPostError(non_downloadable_reason)

    download_link = get_download_link()
    download_link.wait_for(state="visible", timeout=10000)
    download_href = download_link.get_attribute("href")
    if not download_href:
        raise RuntimeError(f"Download link missing href: {post_url}")

    download_url = urljoin(post_url, download_href)
    download_attribute = download_link.get_attribute("download")
    return args.output / resolve_download_filename(download_url, download_attribute)


def download_post_asset(output_path: Path) -> None:
    download_link = get_download_link()
    with download_page.expect_download(timeout=args.timeout_ms) as download_info:
        download_link.click()
    download = download_info.value
    download.save_as(output_path)


def process_posts(posts: list[Any], page_number: int, seen_post_ids: set[str]) -> None:
    progress = tqdm(posts, desc=f"Page {page_number}", unit="post", leave=False, position=1, file=sys.stderr)
    for index, post in enumerate(progress, start=1):
        post_id = get_post_id(post)
        if not post_id:
            log(f"[yellow]Skipped page[/yellow] {page_number} post {index}: invalid post id")
            continue
        elif post_id in seen_post_ids:
            log(f"[yellow]Skipped page[/yellow] {page_number} post {index}: duplicate post id {post_id}")
            continue

        seen_post_ids.add(post_id)

        post_hash = get_post_hash(post)
        if post_hash and post_hash in existing_file_hashes:
            log(f"[yellow]Skipped page[/yellow] {page_number} post {index}: hash already exists {post_hash}")
            continue

        try:
            output_path = prepare_download(build_post_url(post_id))
        except SkipPostError as error:
            log(f"[yellow]Skipped page[/yellow] {page_number} post {index}: {get_error_message(error)}")
            continue
        except Exception as error:
            log(f"[red]Failed page[/red] {page_number} post {index}: {get_error_message(error)}")
            delay(REQUEST_DELAY_MS)
            continue

        if output_path.exists():
            log(f"[yellow]Skipped page[/yellow] {page_number} post {index}: file already exists")
            continue

        try:
            download_post_asset(output_path)
        except Exception as error:
            log(f"[red]Failed page[/red] {page_number} post {index}: {get_error_message(error)}")

        delay(REQUEST_DELAY_MS)


def run_browser_scrape() -> None:
    global download_page
    assert args is not None

    args.output.mkdir(parents=True, exist_ok=True)
    args.profile_dir.mkdir(parents=True, exist_ok=True)
    initialize_existing_file_hashes(args.output)
    assert existing_file_hashes is not None

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(args.profile_dir),
            headless=args.headless,
            no_viewport=True,
            accept_downloads=True,
        )

        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            wait_for_challenge_clear(page)

            total_pages, _, cached_pages = fetch_total_pages(page)
            log(f"[green]Total pages:[/green] {total_pages}")

            download_page = context.new_page()
            assert download_page is not None
            seen_post_ids: set[str] = set()

            with tqdm(
                range(1, total_pages + 1), desc="Processing pages", unit="page", position=0, file=sys.stderr
            ) as outer_progress:
                for page_number in outer_progress:
                    posts = (
                        cached_pages[page_number - 1] if cached_pages is not None else fetch_posts(page, page_number)
                    )
                    process_posts(posts, page_number, seen_post_ids)
        finally:
            download_page = cast(Page, None)
            context.close()


def main() -> None:
    load_args()
    run_browser_scrape()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as error:
        log(get_error_message(error))
        raise SystemExit(1)
