@echo off
rem Builds a standalone dist\SessionDeck.exe (no Python needed on target PCs)
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller || exit /b 1
py -m PyInstaller --noconfirm --clean --onefile --windowed --name SessionDeck sessiondeck.pyw || exit /b 1
echo.
echo Built: %~dp0dist\SessionDeck.exe
