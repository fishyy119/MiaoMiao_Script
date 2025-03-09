"""
input: 要处理的文件夹路径
output: 将符合后缀的文件提取到结果目录中，并按第一级目录名称分类
"""

from pathlib import Path
import shutil
from typing import List


def remove_empty_dirs(directory: Path) -> None:
    """
    删除该目录下所有空子目录
    """
    for sub_dir in directory.iterdir():
        if sub_dir.is_dir() and not any(sub_dir.iterdir()):
            sub_dir.rmdir()


def extract_files(
    src_dir: Path, dest_dir_root: Path, white_list: List[str], ignore_dest_dir: bool = True, disable_sort: bool = False
) -> None:
    """
    提取指定后缀的文件夹到结果目录。

    Args:
        src_dir (Path): 要搜索文件的源目录。
        dest_dir_root (Path): 保存提取文件的根目录。s
        white_list (List[str]): 要提取的文件后缀列表。
        ignore_dest_dir (bool, optional): 如果为True，则忽略源目录中与结果目录同名的目录。默认为True。
        disable_sort (bool, optional): 如果为True，则禁用将文件分类到子目录中。默认为False。
    """
    for ext in white_list:
        # 生成结果目录
        dest_dir = dest_dir_root / ext.upper()
        if dest_dir.exists():
            confirm = input(f"目标目录'{dest_dir}'已存在，按y删除并继续: ")
            if confirm.lower() == "y":
                shutil.rmtree(dest_dir)
            else:
                continue
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 遍历处理
        for sub_dir in src_dir.iterdir():
            if sub_dir.is_dir():
                if sub_dir.name == dest_dir.name and ignore_dest_dir:
                    continue

                dest_sub_dir = dest_dir / sub_dir.name
                dest_sub_dir.mkdir(parents=True, exist_ok=True)

                for file_path in sub_dir.rglob(f"*{ext}"):
                    if file_path.is_file():
                        if disable_sort:
                            dest_file_path = dest_dir / file_path.name
                        else:
                            dest_file_path = dest_sub_dir / file_path.name

                        # 同名文件加个后缀
                        if dest_file_path.exists():
                            dest_file_path = (
                                dest_sub_dir / f"{file_path.stem}_{file_path.stat().st_mtime}{file_path.suffix}"
                            )
                        shutil.copy(file_path, dest_file_path)
        remove_empty_dirs(dest_dir)


if __name__ == "__main__":
    src_dir = input("输入路径: ")
    white_list = [".torrent"]
    extract_files(Path(src_dir), Path(src_dir), white_list=white_list, disable_sort=False, ignore_dest_dir=True)
