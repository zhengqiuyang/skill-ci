@echo off
rem skill-lint launcher (Windows cmd.exe).
rem
rem Locates the skill-ci repository root relative to this script, puts
rem <root>\src on PYTHONPATH and runs the linter. Installs nothing, writes
rem nothing outside the target/report the user asks for.
rem
rem Usage: bin\skill-lint.cmd <target> [options...]
rem   Same arguments as `python -m skill_ci` (see --help).

setlocal
set "SCRIPT_DIR=%~dp0"
rem Strip the trailing backslash so the ".." join is unambiguous.
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "REPO_ROOT=%%~fI"

if not exist "%REPO_ROOT%\src\skill_ci" (
    echo skill-lint: cannot locate skill_ci sources under %REPO_ROOT%\src 1>&2
    exit /b 2
)

set "PYTHONPATH=%REPO_ROOT%\src;%PYTHONPATH%"
python -m skill_ci %*
endlocal & exit /b %ERRORLEVEL%
