@echo off
setlocal

call "%~dp0tools\start_invoice_app.bat"
exit /b %errorlevel%
