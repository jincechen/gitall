@echo off
rem Windows launcher: lets you type  gitall ...  once this folder is on your PATH.
where py >nul 2>nul && (py -3 "%~dpn0.py" %* & exit /b)
python "%~dpn0.py" %*
