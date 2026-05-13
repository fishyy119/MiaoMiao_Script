import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4.element import Tag

DEFAULT_USER_AGENT = "Mozilla/5.0"
DEFAULT_HTML_TIMEOUT_SECONDS = 10
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 15
MAX_FILENAME_LENGTH = 64
FILENAME_HASH_LENGTH = 16


def build_session(user_agent: str = DEFAULT_USER_AGENT) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    return session


def get_tag_attr(tag: Tag, name: str) -> str | None:
    value = tag.get(name)
    return value if isinstance(value, str) else None


def normalize_url(base_url: str, target_url: str) -> str:
    absolute_url = urljoin(base_url, target_url)
    parsed = urlparse(absolute_url)
    return urlunparse(parsed._replace(fragment=""))


def get_filename_from_url(url: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    filename = Path(urlparse(url).path).name
    if not filename:
        raise RuntimeError(f"Invalid file URL: {url}")

    if len(filename) <= max_length:
        return filename

    suffix = Path(filename).suffix
    stem = Path(filename).stem
    hash_suffix = hashlib.blake2s(url.encode("utf-8"), digest_size=FILENAME_HASH_LENGTH // 2).hexdigest()
    max_stem_length = max_length - (1 + len(hash_suffix) + len(suffix))

    return f"{stem[:max_stem_length]}-{hash_suffix}{suffix}"


def fetch_html(
    session: requests.Session,
    url: str,
    referer: str | None = None,
    timeout: int = DEFAULT_HTML_TIMEOUT_SECONDS,
) -> str:
    headers = {"Referer": referer} if referer else None
    response = session.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_json(
    session: requests.Session,
    url: str,
    referer: str | None = None,
    timeout: int = DEFAULT_HTML_TIMEOUT_SECONDS,
) -> Any:
    headers = {"Referer": referer} if referer else None
    response = session.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def download_file(
    session: requests.Session,
    url: str,
    output_path: Path,
    referer: str | None = None,
    timeout: int = DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
) -> Path:
    if output_path.exists():
        return output_path

    headers = {"Referer": referer} if referer else None
    with session.get(url, headers=headers, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with output_path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file_obj.write(chunk)

    return output_path


def download_url_to_directory(
    session: requests.Session,
    url: str,
    output_dir: Path,
    referer: str | None = None,
    timeout: int = DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
) -> Path:
    output_path = output_dir / get_filename_from_url(url)
    return download_file(session, url, output_path, referer=referer, timeout=timeout)
