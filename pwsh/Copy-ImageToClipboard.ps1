param(
    [string]$Path = $args[0]
)

# 必须在 STA 线程下运行
if ([Threading.Thread]::CurrentThread.ApartmentState -ne "STA") {
    Write-Error "This script must be run with -STA."
    exit 1
}

Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName WindowsBase

try {
    # 使用 WPF BitmapImage（基于 WIC）
    # 转换为绝对路径，不解析特殊字符
    $file = Get-Item -LiteralPath $Path -ErrorAction Stop
    $fullPath = $file.FullName

    # 构造 file:// URI
    $uri = New-Object System.Uri($fullPath, [System.UriKind]::Absolute)

    $bitmap = New-Object System.Windows.Media.Imaging.BitmapImage
    $bitmap.BeginInit()
    $bitmap.CacheOption = [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad
    $bitmap.UriSource = $uri
    $bitmap.EndInit()
    $bitmap.Freeze()  # 提高稳定性，避免线程问题

    # 写入剪贴板
    [System.Windows.Clipboard]::SetImage($bitmap)

}
catch {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        $_.Exception.Message,
        "Copy Image Error",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    )
}