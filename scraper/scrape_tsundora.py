#pyright: standard
import _pre_init
import argparse
import math
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from utils import build_session, download_url_to_directory, fetch_html, get_tag_attr, normalize_url


REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 30
PAGE_PATH_RE = re.compile(r"/page/\d+/?$")


def log(message: str) -> None:
    tqdm.write(message)


class CliArgs(argparse.Namespace):
    url: str
    output: str | None
    timeout: int


def build_first_page_url(url: str) -> str:
    parsed = urlparse(url)
    path = PAGE_PATH_RE.sub("/", parsed.path)
    if not path:
        path = "/"
    return urlunparse(parsed._replace(path=path))


def build_page_url(first_page_url: str, page: int) -> str:
    if page <= 1:
        return first_page_url

    parsed = urlparse(first_page_url)
    base_path = parsed.path.rstrip("/")
    page_path = f"{base_path}/page/{page}" if base_path else f"/page/{page}"
    return urlunparse(parsed._replace(path=page_path))


def parse_posts_per_page(soup: BeautifulSoup) -> int:
    return len(soup.select("main#main .article_content > article.article-box > a.article-item[href]"))


def parse_listing_post_urls(page_url: str, soup: BeautifulSoup) -> list[str]:
    post_urls: list[str] = []
    for anchor in soup.select("main#main .article_content > article.article-box > a.article-item[href]"):
        href = get_tag_attr(anchor, "href")
        if href:
            post_urls.append(normalize_url(page_url, href))
    return post_urls


def parse_total_posts(soup: BeautifulSoup) -> int | None:
    title = soup.select_one("main#main header.page-header h1.page-title")
    if not title:
        return None

    text = title.get_text(" ", strip=True)
    match = re.search(r"\((\d+)\)", text)
    if not match:
        return None

    return int(match.group(1))


def parse_total_pages(soup: BeautifulSoup) -> int:
    visible_page_numbers: list[int] = []
    for node in soup.select("nav.navigation.pagination .page-numbers"):
        text = node.get_text(strip=True)
        if text.isdigit():
            visible_page_numbers.append(int(text))

    total_pages = max(visible_page_numbers, default=1)
    posts_per_page = parse_posts_per_page(soup)
    total_posts = parse_total_posts(soup)

    if total_posts and posts_per_page > 0:
        derived_total_pages = math.ceil(total_posts / posts_per_page)
        total_pages = max(total_pages, derived_total_pages)

    return max(total_pages, 1)


def parse_image_page_url(post_url: str, soup: BeautifulSoup) -> str | None:
    anchor = soup.select_one("main#main figure.article-thumb > a[href]")
    if not anchor:
        return None

    href = get_tag_attr(anchor, "href")
    if not href:
        return None

    return normalize_url(post_url, href)


def parse_original_image_url(image_page_url: str, soup: BeautifulSoup) -> str | None:
    image = soup.select_one("body > img[src]")
    if not image:
        return None

    src = get_tag_attr(image, "src")
    if not src:
        return None

    return normalize_url(image_page_url, src)


def parse_og_image_url(post_url: str, soup: BeautifulSoup) -> str | None:
    meta = soup.select_one("meta[property='og:image'][content]")
    if not meta:
        return None

    content = get_tag_attr(meta, "content")
    if not content:
        return None

    return normalize_url(post_url, content)


def resolve_image_url(session: requests.Session, post_url: str) -> str:
    post_html = fetch_html(session, post_url, timeout=REQUEST_TIMEOUT_SECONDS)
    post_soup = BeautifulSoup(post_html, "html.parser")

    image_page_url = parse_image_page_url(post_url, post_soup)
    if image_page_url:
        image_page_html = fetch_html(session, image_page_url, referer=post_url, timeout=REQUEST_TIMEOUT_SECONDS)
        image_page_soup = BeautifulSoup(image_page_html, "html.parser")
        image_url = parse_original_image_url(image_page_url, image_page_soup)
        if image_url:
            return image_url

    og_image_url = parse_og_image_url(post_url, post_soup)
    if og_image_url:
        return og_image_url

    raise RuntimeError("Failed to resolve original image URL")


def process_page(
    base_url: str,
    page: int,
    session: requests.Session,
    output_dir: Path,
) -> None:
    page_url = build_page_url(base_url, page)
    html = fetch_html(session, page_url, timeout=REQUEST_TIMEOUT_SECONDS)
    soup = BeautifulSoup(html, "html.parser")
    post_urls = parse_listing_post_urls(page_url, soup)

    progress = tqdm(post_urls, desc=f"Page {page}", unit="post", leave=False, position=1)
    for post_url in progress:
        try:
            image_url = resolve_image_url(session, post_url)
            download_url_to_directory(
                session,
                image_url,
                output_dir,
                referer=post_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            progress.write(f"Failed to process {post_url}: {exc}")

        time.sleep(REQUEST_DELAY_SECONDS)


def crawl_listing(start_url: str, output_dir: Path) -> None:
    session = build_session()
    first_page_url = build_first_page_url(start_url)

    log(f"Fetching first page: {first_page_url}")
    first_page_html = fetch_html(session, first_page_url, timeout=REQUEST_TIMEOUT_SECONDS)
    first_page_soup = BeautifulSoup(first_page_html, "html.parser")
    total_pages = parse_total_pages(first_page_soup)
    log(f"Total pages: {total_pages}")

    outer_progress = tqdm(range(1, total_pages + 1), desc="Processing pages", unit="page", position=0)
    for page_number in outer_progress:
        page_url = build_page_url(first_page_url, page_number)
        outer_progress.set_postfix_str(page_url, refresh=False)

        process_page(
            base_url=first_page_url,
            page=page_number,
            session=session,
            output_dir=output_dir,
        )


def main() -> None:
    global REQUEST_TIMEOUT_SECONDS

    parser = argparse.ArgumentParser(description="Tsundora 图片抓取脚本")
    parser.add_argument("url", type=str, help="目标网页 URL")
    parser.add_argument("-o", "--output", type=str, default=None, help="图片保存目录 (默认: .tsundora)")
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT_SECONDS, help="请求超时秒数 (默认: 30)")
    args = parser.parse_args(namespace=CliArgs())
    REQUEST_TIMEOUT_SECONDS = args.timeout

    output_dir = Path(args.output) if args.output else Path(__file__).parent / ".tsundora"
    output_dir.mkdir(parents=True, exist_ok=True)

    crawl_listing(args.url, output_dir)


if __name__ == "__main__":
    main()
