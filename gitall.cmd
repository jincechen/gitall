@echo off
rem Windows launcher: lets you type  gitall ...  once this folder is on your PATH.
rem Prefers the py launcher, falls back to python; passes gitall's exit code on.
where py >nul 2>nul || goto python
py -3 "%~dpn0.py" %*
exit /b %ERRORLEVEL%
:python
python "%~dpn0.py" %*
exit /b %ERRORLEVEL%
