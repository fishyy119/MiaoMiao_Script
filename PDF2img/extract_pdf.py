# pyright: standard
import argparse
import io
from dataclasses import dataclass
from pathlib import Path
from typing import List

import fitz
import pymupdf
from PIL import Image
from rich import print
from tqdm import tqdm

HERE = Path(__file__).parent


@dataclass
class Args:
    pdf_path: Path
    pdf_document: fitz.Document
    output_folder: Path
    dpi: int
    page_numbers: List[int]

    @classmethod
    def from_namespace(cls, ns: argparse.Namespace) -> "Args":
        pdf_path = Path(ns.pdf_path)

        output_folder = Path(ns.output_folder) if ns.output_folder is not None else HERE / ".pdf_pages"
        output_folder.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(pdf_path)
        if ns.pages is None:
            page_numbers = list(range(doc.page_count))
        else:
            page_numbers = [p - 1 for p in ns.pages]

        return cls(
            pdf_path=pdf_path,
            pdf_document=doc,
            output_folder=output_folder,
            dpi=ns.dpi,
            page_numbers=page_numbers,
        )


def parse_args():
    parser = argparse.ArgumentParser(description="Extract PDF pages as high-quality JPG images.")
    parser.add_argument("pdf_path", type=Path, help="Path to the input PDF file.")
    parser.add_argument("--output_folder", "-o", type=str, required=False, help="Folder to save the extracted images.")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for rendering the images (default: 300).")
    parser.add_argument(
        "--pages",
        "-p",
        type=int,
        nargs="+",
        help="Specific page numbers to extract (1-based index). If not provided, all pages will be extracted.",
    )
    args = parser.parse_args()

    return Args.from_namespace(args)


def extract_pages_as_images(args: Args) -> None:
    # 打开PDF文件
    pdf_document = args.pdf_document
    for page_number in tqdm(args.page_numbers, desc="Processing pages"):
        page = pdf_document.load_page(page_number)  # pyright: ignore[reportAttributeAccessIssue]

        # 设置渲染的DPI
        zoom_x = args.dpi / 72  # 72 DPI 是 PDF 默认的 DPI
        zoom_y = args.dpi / 72

        # 渲染页面为图像
        pix: pymupdf.Pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom_x, zoom_y))
        img_bytes: bytes = pix.pil_tobytes(format="jpeg")  # 转换为 JPEG 格式的字节数据
        image_filename = f"{page_number + 1:04d}.jpg"
        image_path = args.output_folder / image_filename

        # 使用Pillow保存图像为 JPG 格式
        with Image.open(io.BytesIO(img_bytes)) as img:
            img.save(image_path, format="JPEG", quality=100, optimize=True)

    print(f"提取完成，共提取了 {len(args.page_numbers)} 页。")


def main():
    args = parse_args()
    try:
        extract_pages_as_images(args)
    finally:
        args.pdf_document.close()


if __name__ == "__main__":
    main()
