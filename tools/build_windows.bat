@echo off
setlocal EnableExtensions

pushd "%~dp0\.."
if errorlevel 1 goto :error

set "PYTHON_VERSION=3.11.9"
set "PYTHON_INSTALLER=%TEMP%\python-%PYTHON_VERSION%-amd64.exe"
set "BOOTSTRAP_PYTHON_EXE="
set "BOOTSTRAP_PYTHON_ARGS="
set "VENV_DIR=.venv_windows"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

if exist "%VENV_PYTHON%" goto venv_ready

call :find_python
if defined BOOTSTRAP_PYTHON_EXE goto create_venv

where winget >nul 2>nul
if not errorlevel 1 (
    echo [INFO] Python 3 not found. Trying winget installation first...
    call :install_python_with_winget
    call :find_python
    if defined BOOTSTRAP_PYTHON_EXE goto create_venv
)

echo [INFO] Trying direct Python installer from python.org...
call :install_python_with_direct_download
call :find_python
if defined BOOTSTRAP_PYTHON_EXE goto create_venv

:python_missing
echo [ERROR] Python 3 was not found.
echo Please install Python 3.9+ and run this script again.
goto :error

:create_venv
echo [1/4] Creating virtual environment...
"%BOOTSTRAP_PYTHON_EXE%" %BOOTSTRAP_PYTHON_ARGS% -m venv "%VENV_DIR%"
if errorlevel 1 goto :error

:venv_ready
echo [2/4] Checking pip...
"%VENV_PYTHON%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [INFO] pip is missing. Restoring pip with ensurepip...
    "%VENV_PYTHON%" -m ensurepip --upgrade
    if errorlevel 1 goto :error
    "%VENV_PYTHON%" -m pip --version >nul 2>nul
    if errorlevel 1 goto :error
)

echo [3/4] Installing dependencies...
"%VENV_PYTHON%" -m pip install --disable-pip-version-check --no-warn-script-location -r source\requirements.txt
if errorlevel 1 goto :error

echo [4/4] Building Windows package...
"%VENV_PYTHON%" -m PyInstaller tools\invoice_organizer_windows.spec --noconfirm --distpath app\windows --workpath build\windows
if errorlevel 1 goto :error

echo.
echo Build completed.
echo Output folder:
echo %CD%\app\windows\PDF发票自动整理归纳工具
echo.
popd
pause
exit /b 0

:error
echo.
echo Build failed. Please check the messages above.
echo.
popd
pause
exit /b 1

:find_python
call :try_launcher py -3
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_launcher python
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%LocalAppData%\Programs\Python\Python313\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%LocalAppData%\Programs\Python\Python312\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%LocalAppData%\Programs\Python\Python311\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%LocalAppData%\Programs\Python\Python310\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%LocalAppData%\Programs\Python\Python39\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%ProgramFiles%\Python313\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%ProgramFiles%\Python312\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%ProgramFiles%\Python311\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%ProgramFiles%\Python310\python.exe"
if defined BOOTSTRAP_PYTHON_EXE goto :eof

call :try_file "%ProgramFiles%\Python39\python.exe"
goto :eof

:install_python_with_winget
winget source reset --force >nul 2>nul
winget source update >nul 2>nul
winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements --scope user
if errorlevel 1 echo [WARN] winget install failed.
goto :eof

:install_python_with_direct_download
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe' -OutFile '%PYTHON_INSTALLER%'"
if errorlevel 1 (
    echo [WARN] Direct download failed.
    goto :eof
)

"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 SimpleInstall=1
if errorlevel 1 (
    echo [WARN] Python installer failed.
    goto :eof
)

timeout /t 3 /nobreak >nul
goto :eof

:try_launcher
"%~1" %~2 --version >nul 2>nul
if not errorlevel 1 (
    set "BOOTSTRAP_PYTHON_EXE=%~1"
    set "BOOTSTRAP_PYTHON_ARGS=%~2"
)
goto :eof

:try_file
if exist "%~1" (
    "%~1" --version >nul 2>nul
    if not errorlevel 1 (
        set "BOOTSTRAP_PYTHON_EXE=%~1"
        set "BOOTSTRAP_PYTHON_ARGS="
    )
)
goto :eof
