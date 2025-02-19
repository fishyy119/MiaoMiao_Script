@echo off
setlocal enabledelayedexpansion

:: 设置目标文件夹路径
set "folderPath=D:\TencentRecv\QQotherFiles\1830979240\nt_qq\nt_data\Video"

:: 遍历文件夹及子文件夹，删除特定格式的文件
for /r "%folderPath%" %%f in (*.jpg *.png *.gif *.jpeg) do (
    echo Deleting: %%f
    del "%%f"
)

echo 完成删除操作
pause