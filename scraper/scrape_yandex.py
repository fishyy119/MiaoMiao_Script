import argparse
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from rich import print
from tqdm import tqdm


def fetch_html(url: str, timeout: int = 10) -> str:
    """获取网页 HTML"""
    headers = {"User-Agent": "Mozilla/5.0"}
    response: requests.Response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def parse_image_links(soup: BeautifulSoup) -> List[str]:
    """从 HTML 中解析图片链接"""
    links: List[str] = []

    for a_tag in soup.find_all("a", class_="directlink largeimg"):
        href: Optional[str] = a_tag.get("href")
        if href:
            links.append(href)

    return links


def parse_total_pages(soup: BeautifulSoup) -> int:
    """解析总页数"""
    page_numbers: List[int] = []
    for a_tag in soup.find_all("a"):
        aria_label = a_tag.get("aria-label", "")
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


def download_image(url: str, output_dir: Path) -> None:
    """下载单张图片"""
    filename: str = Path(urlparse(url).path).name
    save_path: Path = output_dir / filename
    if save_path.exists():
        return

    with requests.get(url, stream=True, timeout=15) as r:
        r.raise_for_status()
        with save_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)


def process_page(base_url: str, page: int, output_dir: Path) -> None:
    parsed = urlparse(base_url)
    query_params = parse_qs(parsed.query)

    # parse_qs 返回的值是列表，统一用列表保存
    query_params["page"] = [str(page)]
    new_query = urlencode(query_params, doseq=True)

    # 构建新 URL
    new_url = urlunparse(parsed._replace(query=new_query))
    html: str = fetch_html(new_url)
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")
    image_links: List[str] = parse_image_links(soup)

    for link in tqdm(image_links, desc="Downloading images", unit="image", leave=False):
        try:
            download_image(link, output_dir)
        except Exception as e:
            print(f"Failed to download {link}: {e}")


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Yandex 图片抓取脚本")
    parser.add_argument("url", type=str, help="目标网页 URL")
    parser.add_argument("-o", "--output", type=str, default=None, help="图片保存目录 (默认: .yandex)")
    args: argparse.Namespace = parser.parse_args()

    output_dir: Path = Path(args.output) if args.output else Path(__file__).parent / ".yandex"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching HTML from {args.url}...")
    html: str = fetch_html(args.url)
    soup: BeautifulSoup = BeautifulSoup(html, "html.parser")

    total_page_count = parse_total_pages(soup)
    print(f"Total pages: {total_page_count}")

    for page in tqdm(range(1, total_page_count + 1), desc="Processing pages", unit="page"):
        try:
            process_page(args.url, page, output_dir)
        except Exception as e:
            print(f"Failed to process page {page}: {e}")


if __name__ == "__main__":
    main()
