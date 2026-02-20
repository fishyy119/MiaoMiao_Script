# pyright: standard
import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from rich import print

HERE = Path(__file__).parent


@dataclass
class Args:
    img1: Path
    img2: Path
    output_folder: Path

    @classmethod
    def from_namespace(cls, ns: argparse.Namespace) -> "Args":
        input_dir = Path(ns.input_dir) if ns.input_dir is not None else HERE / ".pdf_pages"
        img1 = input_dir / f"{ns.pages[0]:04d}.jpg"
        img2 = input_dir / f"{ns.pages[1]:04d}.jpg"

        output_folder = Path(ns.output_dir) if ns.output_dir is not None else HERE / ".concat_results"
        output_folder.mkdir(parents=True, exist_ok=True)

        return cls(img1=img1, img2=img2, output_folder=output_folder)


def parse_args():
    parser = argparse.ArgumentParser(description="Concatenate pairs of images in a directory.")
    parser.add_argument("--input-dir", "-i", type=Path, help="Directory containing input images.")
    parser.add_argument("--pages", "-p", type=int, nargs=2, help="Two page numbers (1-based index).")
    parser.add_argument("--output-dir", "-o", type=Path, help="Directory to save output images.")
    ns = parser.parse_args()

    return Args.from_namespace(ns)


def concat_images(image1_path: Path, image2_path: Path, output_path: Path) -> None:
    img1 = Image.open(image1_path)
    img2 = Image.open(image2_path)

    # 获取图片尺寸
    width1, height1 = img1.size
    width2, height2 = img2.size

    # 创建新图片，宽度为两张图片宽度之和，高度为较高的图片高度
    new_image = Image.new("RGB", (width1 + width2, max(height1, height2)))

    # 粘贴图片
    new_image.paste(img1, (0, 0))
    new_image.paste(img2, (width1, 0))

    # 保存新图片
    new_image.save(output_path)


def main():
    args = parse_args()
    output_path = args.output_folder / f"{args.img1.stem}_{args.img2.stem}.jpg"
    concat_images(args.img1, args.img2, output_path)
    print(f"Concatenated image saved to: {output_path}")


if __name__ == "__main__":
    main()
