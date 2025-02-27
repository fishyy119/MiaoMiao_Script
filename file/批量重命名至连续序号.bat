@echo off
setlocal enabledelayedexpansion

REM 起始序号，人工指定
set /A index=520

del map.txt

REM 遍历当前目录下所有的mp4文件
for %%f in (*.mp4) do (
    REM 获取文件名（不包括扩展名）
    set filename=%%~nf

    ren "!filename!.mp4" !index!.mp4
    echo !index! = !filename! >> map.txt
    echo !index! = !filename!
    set /A index=index+1

)

echo 完成
pause
exit /b

