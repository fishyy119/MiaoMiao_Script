"""
使用ffmpeg批量将 .flac/.wav 文件转换为 .mp3 文件，比特率320k，采样率44.1kHz
input: 待转换文件的父文件夹
output: 在每个存在待转文件的目录下，创建新目录 mp3_files 容纳转换后文件
"""

from pathlib import Path
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import List


def convert_to_mp3(input_file: Path, output_folder: Path) -> None:
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
        str(output_folder / input_file.with_suffix(".mp3").name),
        "-y",  # 自动替换同名文件
    ]
    subprocess.run(command)


def process_files(input_files: List[Path]) -> None:
    """并行处理所有文件"""
    with ThreadPoolExecutor() as executor:
        futures: List[Future[None]] = []
        for file in input_files:
            futures.append(executor.submit(convert_to_mp3, file, generateOutDir(file)))

        # 使用 as_completed 来监视任务的完成情况
        for idx, future in enumerate(as_completed(futures), 1):
            future.result()
            print(f"\r已处理[{idx}/{len(futures)}]", end="", flush=True)


def generateOutDir(file_path: Path) -> Path:
    """拼接输出文件夹路径，同时保证文件夹存在"""
    output_folder: Path = Path(file_path).parent / "mp3_files"
    output_folder.mkdir(parents=True, exist_ok=True)
    return output_folder


def main() -> None:
    folder: str = input("目标文件夹：")
    white_list: List[str] = [".wav", ".flac"]
    input_files: List[Path] = []

    for path in Path(folder).rglob("*"):
        if path.suffix in white_list:
            input_files.append(path)

    print(f"共找到{len(input_files)}个待处理文件...")
    process_files(input_files)


if __name__ == "__main__":
    main()
