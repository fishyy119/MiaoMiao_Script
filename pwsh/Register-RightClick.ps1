param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("ps1", "exe")]
    [string]$Mode = "ps1"
)
# exe格式的封装命令，需要安装ps2exe
# Invoke-ps2exe "C:\Scripts\Copy-ImageToClipboard.ps1" "C:\Scripts\Copy-ImageToClipboard.exe" -noConsole -sta


$menuName = "Copy Image Data"
$formats = ".png", ".jpg", ".jpeg", ".webp", ".bmp"

if ($Mode -eq "ps1") {
    # 使用 PowerShell 执行脚本
    # 会有短暂终端窗口弹出
    $command = "pwsh -NoProfile -STA -WindowStyle Hidden -File `"C:\Scripts\Copy-ImageToClipboard.ps1`" `"%1`""
}
else {
    # ! 可执行文件不可使用引号包裹，会解析不出来。
    # ! 因此此处不考虑路径带空格的兼容性，路径不得有空格
    $command = "C:\Scripts\Copy-ImageToClipboard.exe `"%1`""
}


foreach ($ext in $formats) {
    $basePath = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\CopyImageData"

    New-Item -Path $basePath -Force | Out-Null
    Set-ItemProperty -Path $basePath -Name "(default)" -Value $menuName

    New-Item -Path "$basePath\command" -Force | Out-Null

    # 直接拼接 command 字符串
    Set-ItemProperty -Path "$basePath\command" -Name "(default)" -Value $command

    
    # 可选：给菜单加图标
    # Set-ItemProperty -Path $basePath -Name "Icon" -Value "shell32.dll,70"
}

Write-Host "Right-click menu registered using mode: $Mode"