"""
input: 要处理的文件夹路径
output: 将符合后缀的文件提取到结果目录中，并按第一级目录名称分类
"""

from pathlib import Path
import shutil
from typing import List


def extract_files(src_dir: Path, dest_dir_root: Path, white_list: List[str]) -> None:
    for ext in white_list:
        dest_dir = dest_dir_root / ext.upper()
        dest_dir.mkdir(parents=True, exist_ok=True)

        for sub_dir in src_dir.iterdir():
            if sub_dir.is_dir():
                dest_sub_dir = dest_dir / sub_dir.name
                dest_sub_dir.mkdir(parents=True, exist_ok=True)

                for file_path in sub_dir.rglob(f"*{ext}"):
                    shutil.copy(file_path, dest_sub_dir / file_path.name)


if __name__ == "__main__":
    src_dir = input("输入路径: ")
    white_list = [".torrent"]
    extract_files(Path(src_dir), Path(src_dir), white_list=white_list)
