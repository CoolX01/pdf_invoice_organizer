@echo off
setlocal

call "%~dp0tools\build_windows.bat"
exit /b %errorlevel%
