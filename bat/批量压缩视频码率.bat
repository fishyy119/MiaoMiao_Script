@echo off
setlocal enabledelayedexpansion

REM 此处指定目标码率（例如：1000k）
set target_bitrate=1500k

REM 结果文件夹的创建
mkdir result

REM 遍历当前目录下所有的mp4文件
for %%f in (*.mp4) do (
    REM 获取文件名（不包括扩展名）
    set filename=%%~nf
    

    REM 压缩视频文件
    echo 开始压缩：!filename!
    ffmpeg -i "%%f" -b:v %target_bitrate% -loglevel error "result\!filename!.mp4"
    echo 已压缩：!filename!

)

echo 压缩完成！
pause
