@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\build_desktop_exe.ps1"
if errorlevel 1 (
 echo.
 echo Build did not complete. Read the error above.
 pause
 exit /b 1
)
echo.
echo Build finished. Your Windows desktop application is in the dist folder.
pause
