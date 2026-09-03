@echo off
REM ============================================================================
REM The Fool Installer for Windows (CMD wrapper)
REM ============================================================================
REM This batch file launches the PowerShell installer for users running CMD.

setlocal
set "SCRIPT_DIR=%~dp0"

echo.
echo  The Fool Installer
echo  Launching PowerShell installer...
echo.

if exist "%SCRIPT_DIR%install.ps1" (
    powershell -ExecutionPolicy ByPass -NoProfile -File "%SCRIPT_DIR%install.ps1" %*
) else (
    powershell -ExecutionPolicy ByPass -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; & ([scriptblock]::Create((iwr -UseBasicParsing 'https://raw.githubusercontent.com/zaorenn/fool-agent/main/scripts/install.ps1').Content))" %*
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  Installation failed. Please try running PowerShell directly:
    echo    powershell -ExecutionPolicy ByPass -File "%SCRIPT_DIR%install.ps1"
    echo.
    pause
    exit /b 1
)
