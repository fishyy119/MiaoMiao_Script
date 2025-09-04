"""
使用ffmpeg批量将 .flac/.wav 文件转换为 .mp3 文件，比特率320k，采样率44.1kHz
input: 待转换文件的父文件夹
output: 在父文件夹同级处创建备份文件夹，父文件夹中转换成功的.mp3文件会原地替换掉转换前文件
"""

import subprocess
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from shutil import Error, copytree
from typing import List


def convert_to_mp3(input_file: Path) -> None:
    """执行ffmpeg命令，将音频文件转换为mp3格式"""
    command = [
        "ffmpeg",
        "-i",
        str(input_file),
        "-codec:v",  # 复制封面
        "copy",
        "-codec:a",  # 音频编码器
        "libmp3lame",
        "-b:a",  # 音频比特率
        "320k",
        "-ar",  # 采样率
        "44100",
        "-ac",  # 声道
        "2",
        "-loglevel",  # 仅输出error
        "error",
        str(input_file.with_suffix(".mp3")),
        "-y",  # 自动替换同名文件
    ]
    result = subprocess.run(command)
    if result.returncode == 0:
        input_file.unlink()  # 删除原始文件


def process_files(input_files: List[Path]) -> None:
    """并行处理所有文件"""
    with ThreadPoolExecutor() as executor:
        futures: List[Future[None]] = []
        for file in input_files:
            futures.append(
                executor.submit(
                    convert_to_mp3,
                    file,
                )
            )

        # 使用 as_completed 来监视任务的完成情况
        for idx, future in enumerate(as_completed(futures), 1):
            future.result()
            print(f"\r已处理[{idx}/{len(futures)}]", end="", flush=True)


def main() -> None:
    folder: Path = Path(input("目标文件夹："))
    # 复制目标文件夹并加上后缀 .bak
    backup_folder: Path = folder.with_name(folder.name + ".bak")
    try:
        folder_size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
        copy_flag = True
        print(f"正在备份文件夹，文件夹大小: {folder_size / (1024 * 1024):.2f} MB")
        if folder_size / (1024**3) > 3:
            copy_confirm = input("文件过大，是否继续备份(y/[n])")
            if copy_confirm != "y":
                copy_flag = False
        if copy_flag:
            copytree(folder, backup_folder)
            print(f"已创建备份文件夹：{backup_folder}")
    except Error as e:
        print(f"备份过程中发生错误：{e}")

    white_list: List[str] = [".wav", ".flac", ".dsf"]
    input_files: List[Path] = []

    for path in folder.rglob("*"):
        if path.suffix in white_list:
            input_files.append(path)

    print(f"共找到{len(input_files)}个待处理文件...")
    process_files(input_files)


if __name__ == "__main__":
    main()
