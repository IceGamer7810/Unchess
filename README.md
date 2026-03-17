# Unchess Client Desktop

This repository is the future desktop rewrite of the Unchess client.

## Current state

- Flutter/Dart base structure
- Windows desktop build script
- placeholder application shell
- clean repository intended for the non-Python client rewrite

## Build

Requirements:

- local Flutter SDK
- local JDK
- Windows desktop tooling enabled for Flutter
- Windows C++/MSVC build toolchain for Flutter desktop

Expected local tool layout:

- `d:\GitHub\Unchess\Tools\flutter`
- `d:\GitHub\Unchess\Tools\jdk`
- optional shared Android tooling under `d:\GitHub\Unchess\Tools\android-sdk`

Suggested download sources:

- Flutter SDK:
  - `https://docs.flutter.dev/get-started/install/windows/desktop`
  - archive source used here:
    - `https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json`
- JDK 17:
  - `https://adoptium.net/temurin/releases/`
- Windows desktop build tooling:
  - Visual Studio Build Tools / Desktop development with C++
  - `https://visualstudio.microsoft.com/downloads/`

Build command:

```bat
build_desktop.bat
```

The script will:

1. generate missing Windows Flutter platform files if needed
2. run `flutter pub get`
3. build the Windows desktop client

Important:

- the current `build_desktop.bat` is only the repo-side wrapper
- it still needs to be updated to use the local `Tools` folder explicitly instead of relying on `PATH`
- the desktop rewrite is not ready to build the real game yet; this is only the initial Flutter base

## Planned direction

- carry over the existing Unchess gameplay and multiplayer protocol from the Python client
- build a proper desktop-focused UI with a cleaner architecture than the old monolithic client
