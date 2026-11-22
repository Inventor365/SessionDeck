@echo off
rem CLI launcher: `sessiondeck` opens the GUI, `sessiondeck ls` etc. run commands
if exist "%~dp0dist\SessionDeck.exe" (
  if "%~1"=="" (start "" "%~dp0dist\SessionDeck.exe") else ("%~dp0dist\SessionDeck.exe" %*)
) else (
  if "%~1"=="" (start "" pyw "%~dp0sessiondeck.pyw") else (py "%~dp0sessiondeck.pyw" %*)
)
