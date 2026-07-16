# Setup Windows

## Requirements

- Windows 10 or 11.
- Python 3 installed and available through `py -3`.
- Chrome installed for visible Playwright browser mode.
- Internet access for first setup package installation.

## Install

```bat
cd /d C:\Users\lucia\Documents\Codex\2026-06-27\https-chatgpt-com-c-6a3f403a-8d04\GodTranslator_Desktop_Companion
SETUP_ONCE.bat
```

The setup script creates `.venv`, installs Python dependencies, and installs the Playwright Chromium browser runtime.

## Run

```bat
RUN_GODTRANSLATOR_DESKTOP.bat
```

## Local Data

The application writes local data to:

```text
%LOCALAPPDATA%\GodTranslatorDesktop
```

Folders:

- `downloads`
- `manifests`
- `logs`
- `packs`
- `library_cache`
- `browser_profiles`

You can change the downloads folder later from Settings. Browser profiles remain local and are never included in packs.

## Verification

```bat
.venv\Scripts\python.exe -m py_compile app.py desktop_companion\*.py desktop_companion\adapters\*.py
.venv\Scripts\python.exe -m unittest discover -s tests
```
