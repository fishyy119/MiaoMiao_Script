@echo off
setlocal enabledelayedexpansion

:: 创建保存mp3文件的目录
mkdir mp3_files

:: 遍历当前目录下的所有wav和flac文件
for /r %%d in (*.wav *.flac) do (
    echo Converting: %%~nd
    ffmpeg -i "%%d" -codec:a libmp3lame -b:a 320k -ar 44100 -ac 2 -loglevel error "mp3_files/%%~nd.mp3"
)

echo All files have been processed.
pause
