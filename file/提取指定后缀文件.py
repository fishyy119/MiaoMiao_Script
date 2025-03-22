"""
input: 要处理的文件夹路径
output: 将符合后缀的文件提取到结果目录中，并按第一级目录名称分类
"""

from pathlib import Path
import hashlib
import shutil
from typing import List


# TODO: 统计


def calculate_md5(file_path: Path, chunk_size: int = 8192) -> str:
    """计算文件的 MD5 哈希值"""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def remove_empty_dirs(directory: Path) -> None:
    """
    删除该目录下所有空子目录
    """
    for sub_dir in directory.iterdir():
        if sub_dir.is_dir() and not any(sub_dir.iterdir()):
            sub_dir.rmdir()


def copy_with_md5_check(src_path: Path, dest_path: Path) -> None:
    """如果目标文件存在，检查 MD5，相同则跳过，不同则加 MD5 后缀"""
    if dest_path.exists():
        src_md5 = calculate_md5(src_path)
        dest_md5 = calculate_md5(dest_path)

        if src_md5 == dest_md5:
            return

        # 生成新的文件路径，添加 MD5 哈希前 8 位作为后缀
        new_dest_path = dest_path.parent / f"{src_path.stem}.{src_md5[:8]}{src_path.suffix}"
        print(new_dest_path)
        shutil.copy2(src_path, new_dest_path)
    else:
        shutil.copy2(src_path, dest_path)


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

                        copy_with_md5_check(file_path, dest_file_path)
        remove_empty_dirs(dest_dir)


if __name__ == "__main__":
    src_dir = input("输入路径: ")
    # white_list = [".torrent"]
    # white_list = [".mp3"]
    # white_list = [".jpg", ".jpeg", ".png"]
    white_list = [".ass"]

    extract_files(Path(src_dir), Path(src_dir), white_list=white_list, disable_sort=True, ignore_dest_dir=True)
