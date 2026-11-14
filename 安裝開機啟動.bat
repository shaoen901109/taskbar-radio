@echo off
chcp 65001 >nul
set "DIR=%~dp0"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\工作列音樂播放器.lnk"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath=(Get-Command pythonw.exe).Source; $s.Arguments='taskbar_player.py'; $s.WorkingDirectory=$env:DIR.TrimEnd('\'); $s.Save()"
echo 已建立開機啟動捷徑：%LNK%
pause
