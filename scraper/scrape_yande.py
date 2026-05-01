#pyright: standard
import _pre_init
import argparse
from pathlib import Path
from typing import List
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from rich import print
from tqdm import tqdm
from utils import build_session, download_url_to_directory, fetch_html, get_tag_attr


REQUEST_TIMEOUT_SECONDS = 15


def parse_image_links(soup: BeautifulSoup) -> List[str]:
    """从 HTML 中解析图片链接"""
    links: List[str] = []

    for a_tag in soup.find_all("a", class_="directlink largeimg"):
        href = get_tag_attr(a_tag, "href")
        if href:
            links.append(href)

    return links


def parse_total_pages(soup: BeautifulSoup) -> int:
    """解析总页数"""
    page_numbers: List[int] = []
    for a_tag in soup.find_all("a"):
        aria_label = get_tag_attr(a_tag, "aria-label") or ""
        if aria_label.startswith("Page "):
            try:
                page_num = int(aria_label.split(" ")[1])
                page_numbers.append(page_num)
            except ValueError:
                continue
    return max(page_numbers) if page_numbers else 1


def parse_current_page(soup: BeautifulSoup) -> int:
    """解析当前页数"""
    current_page_tag = soup.find("em", class_="current")
    if current_page_tag:
        try:
            return int(current_page_tag.text.strip())
        except ValueError:
            pass
    return 1


def process_page(session: requests.Session, base_url: str, page: int, output_dir: Path) -> None:
    parsed = urlparse(base_url)
    query_params = parse_qs(parsed.query)

    # parse_qs 返回的值是列表，统一用列表保存
    query_params["page"] = [str(page)]
    new_query = urlencode(query_params, doseq=True)

    # 构建新 URL
    new_url = urlunparse(parsed._replace(query=new_query))
    html: str = fetch_html(session, new_url, timeout=REQUEST_TIMEOUT_SECONDS)
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")
    image_links: List[str] = parse_image_links(soup)

    for link in tqdm(image_links, desc="Downloading images", unit="image", leave=False):
        try:            
            download_url_to_directory(session, link, output_dir, timeout=REQUEST_TIMEOUT_SECONDS)
        except Exception as e:
            print(f"Failed to download {link}: {e}")


def main() -> None:
    global REQUEST_TIMEOUT_SECONDS

    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="yande 图片抓取脚本")
    parser.add_argument("url", type=str, help="目标网页 URL")
    parser.add_argument("-o", "--output", type=str, default=None, help="图片保存目录 (默认: .yande)")
    parser.add_argument("--timeout", type=int, default=REQUEST_TIMEOUT_SECONDS, help="请求超时秒数 (默认: 15)")
    args: argparse.Namespace = parser.parse_args()
    REQUEST_TIMEOUT_SECONDS = args.timeout

    output_dir: Path = Path(args.output) if args.output else Path(__file__).parent / ".yande"
    output_dir.mkdir(parents=True, exist_ok=True)
    session: requests.Session = build_session()

    print(f"Fetching HTML from {args.url}...")
    html: str = fetch_html(session, args.url, timeout=REQUEST_TIMEOUT_SECONDS)
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")

    total_page_count = parse_total_pages(soup)
    print(f"Total pages: {total_page_count}")

    for page in tqdm(range(1, total_page_count + 1), desc="Processing pages", unit="page"):
        try:
            process_page(session, args.url, page, output_dir)
        except Exception as e:
            print(f"Failed to process page {page}: {e}")


if __name__ == "__main__":
    main()
