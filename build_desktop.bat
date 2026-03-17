@echo off
setlocal

set "CACHE_ROOT=%~dp0.cache"
set "PUB_CACHE=%CACHE_ROOT%\\pub"
set "GRADLE_USER_HOME=%CACHE_ROOT%\\gradle"
set "TMP=%CACHE_ROOT%\\tmp"
set "TEMP=%CACHE_ROOT%\\tmp"

if not exist "%CACHE_ROOT%" mkdir "%CACHE_ROOT%"
if not exist "%PUB_CACHE%" mkdir "%PUB_CACHE%"
if not exist "%GRADLE_USER_HOME%" mkdir "%GRADLE_USER_HOME%"
if not exist "%TMP%" mkdir "%TMP%"

where flutter >nul 2>nul
if errorlevel 1 (
  echo Flutter SDK was not found in PATH.
  exit /b 1
)

if not exist windows (
  echo Generating Windows Flutter scaffold...
  flutter create --platforms=windows .
  if errorlevel 1 exit /b 1
)

echo Fetching packages...
flutter pub get
if errorlevel 1 exit /b 1

echo Building Windows desktop client...
flutter build windows
if errorlevel 1 exit /b 1

echo Done.
endlocal
