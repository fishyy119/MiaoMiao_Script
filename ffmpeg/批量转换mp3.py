""" 
使用ffmpeg批量将 .flac/.wav 文件转换为 .mp3 文件，比特率320k，采样率44.1kHz
input: 待转换文件的父文件夹
output: 在每个存在待转文件的目录下，创建新目录 mp3_files 容纳转换后文件
"""

import os
import os.path as oph
import subprocess
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed, Future


def convert_to_mp3(input_file: str, output_folder: str) -> None:
    """执行ffmpeg命令，将音频文件转换为mp3格式"""
    command = [
        "ffmpeg",
        "-i",
        input_file,
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "320k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-loglevel",
        "error",
        oph.join(output_folder, oph.splitext(oph.basename(input_file))[0] + ".mp3"),
        "-y",
    ]
    subprocess.run(command)


def process_files(input_files: List[str]) -> None:
    """并行处理所有文件"""
    with ThreadPoolExecutor() as executor:
        futures: List[Future] = []
        for file in input_files:
            futures.append(executor.submit(convert_to_mp3, file, generateOutDir(file)))

        # 使用 as_completed 来监视任务的完成情况
        for idx, future in enumerate(as_completed(futures), 1):
            future.result()
            print(f"\r已处理[{idx}/{len(futures)}]", end="", flush=True)


def generateOutDir(file_path: str) -> str:
    """拼接输出文件夹路径，同时保证文件夹存在"""
    output_folder: str = oph.join(oph.dirname(file_path), "mp3_files")
    os.makedirs(output_folder, exist_ok=True)
    return output_folder


def main() -> None:
    folder: str = input("目标文件夹：")
    white_list: List[str] = [".wav", ".flac"]
    input_files: List[str] = []

    # 预处理
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith(tuple(white_list)):
                input_files.append(oph.join(root, file))

    process_files(input_files)


if __name__ == "__main__":
    main()
