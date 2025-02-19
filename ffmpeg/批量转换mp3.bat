:: ! 变量延迟太蠢了，拿叹号当标记，文件路径中成对的叹号直接给删没了 
:: ! 再也不想用这鬼东西了
@echo off

:: 创建保存mp3文件的目录
mkdir mp3_files

:: 遍历当前目录下的所有wav和flac文件
for /r %%d in (*.wav *.flac) do (

    set f=%%d
    set fn=%%~nd
    :: 开启变量延迟后，文件名中叹号会被去掉，所以先获取文件名再开启变量延迟
    setlocal enabledelayedexpansion

    echo Converting: !f!
    REM echo Executing: ffmpeg -i "!f!" -codec:a libmp3lame -b:a 320k -ar 44100 -ac 2 -loglevel error "mp3_files\!fn!.mp3"

    ffmpeg -i "!f!" -codec:a libmp3lame -b:a 320k -ar 44100 -ac 2 -loglevel error "mp3_files/!fn!.mp3"
)

echo All files have been processed.
pause
