@echo off
chcp 65001 >nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\工作列音樂播放器.lnk" 2>nul
echo 已移除開機啟動捷徑
pause
