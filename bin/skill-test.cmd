@echo off
rem skill-test launcher (Windows cmd.exe).
rem
rem Same launcher semantics as bin\skill-lint.cmd: locates the repo root
rem relative to this script, puts <root>\src on PYTHONPATH and runs the
rem trigger-test command (`python -m skill_ci test`). Installs nothing,
rem no network.
rem
rem Usage: bin\skill-test.cmd <repo> --suite prompts.jsonl [options...]

setlocal
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "REPO_ROOT=%%~fI"

if not exist "%REPO_ROOT%\src\skill_ci" (
    echo skill-test: cannot locate skill_ci sources under %REPO_ROOT%\src 1>&2
    exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"
python -m skill_ci test %*
endlocal & exit /b %ERRORLEVEL%
