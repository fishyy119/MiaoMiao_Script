$menuName = "Copy Image Data"
$scriptPath = "C:\Scripts\Copy-ImageToClipboard.ps1"  # 你的脚本绝对路径
$formats = ".png", ".jpg", ".jpeg", ".webp", ".bmp"

foreach ($ext in $formats) {
    # 右键菜单路径
    $basePath = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\CopyImageData"

    # 创建菜单项
    New-Item -Path $basePath -Force | Out-Null
    Set-ItemProperty -Path $basePath -Name "(default)" -Value $menuName

    # 创建命令
    New-Item -Path "$basePath\command" -Force | Out-Null
    $command = "pwsh -NoProfile -STA -WindowStyle Hidden -File `"$scriptPath`" `"%1`""
    Set-ItemProperty -Path "$basePath\command" -Name "(default)" -Value $command

    # 可选：给菜单加图标
    # Set-ItemProperty -Path $basePath -Name "Icon" -Value "shell32.dll,70"
}