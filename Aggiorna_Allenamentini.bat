@echo off
rem Doppio clic per aggiornare Allenamentini con gli ultimi dati Garmin
cd /d "%~dp0"
py garmin_sito.py
if errorlevel 1 pause
