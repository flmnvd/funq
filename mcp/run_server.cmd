@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Create the MCP virtual environment as described in README.md. 1>&2
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -B "%~dp0run_server.py" %*
exit /b %ERRORLEVEL%
