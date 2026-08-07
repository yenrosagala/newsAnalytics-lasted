# Running NewsAnalytics AI as a Windows App

You have two options, from easiest to most "real app"-like.

---

## Option A — Double-click launcher (recommended to start)

No build step, no PyInstaller, works today.

1. Put `run_app.bat` in the root of your project (next to `streamlit_app.py`).
2. Make sure Python 3.10-3.12 is installed and on PATH (python.org installer,
   check "Add python.exe to PATH").
3. Double-click `run_app.bat`.
   - First run: creates a `venv/` folder and installs `requirements.txt`
     (takes a minute or two).
   - Every run after that: starts in a few seconds and opens your default
     browser to the app.
4. To close the app, close the black console window that opened.

This is genuinely how most people should run Streamlit apps locally — it's
simple and doesn't fight Streamlit's internals. Use Option B only if you
specifically want a standalone `.exe` with its own app window (no browser
tab, no visible console, double-click-to-run without Python pre-installed
by the end user).

---

## Option B — Standalone .exe with a native app window

This bundles Python + all dependencies + a native window (via `pywebview`)
into a `.exe` that end users can run without installing Python themselves.

### 1. Install build-only dependencies

```powershell
pip install pyinstaller pywebview
```

(`pywebview` on Windows uses the OS's built-in Edge WebView2 runtime, which
ships with Windows 10/11 by default — no extra runtime to bundle.)

### 2. Build

From the project root (same folder as `streamlit_app.py`), run:

```powershell
pyinstaller --noconfirm --onedir --windowed ^
  --name "NewsAnalyticsAI" ^
  --add-data "app;app" ^
  --add-data "pages;pages" ^
  --add-data "streamlit_app.py;." ^
  --add-data "requirements.txt;." ^
  --collect-all streamlit ^
  --collect-all supabase ^
  --collect-data streamlit ^
  --hidden-import streamlit.web.cli ^
  --hidden-import webview.platforms.edgechromium ^
  desktop_launcher.py
```

Notes on the flags (these matter — Streamlit is notoriously fussy to freeze):

- **`--onedir`, not `--onefile`.** `--onefile` re-extracts the entire bundle
  to a temp folder on *every* launch, which is slow (10-30s) and more
  failure-prone with Streamlit's static assets. `--onedir` produces a folder
  you can zip/ship instead, and starts in a couple seconds.
- **`--collect-all streamlit`** pulls in Streamlit's static frontend files
  and metadata that PyInstaller's dependency scanner doesn't find on its
  own (this is the #1 cause of frozen Streamlit apps showing a blank page).
- **`--collect-all supabase`** — same reason, for the Supabase client's
  packaged metadata.
- **`--add-data "app;app"`** and **`--add-data "pages;pages"`** bundle your
  own source folders as data (Streamlit imports page files by path at
  runtime, not as regular Python imports, so PyInstaller's import scanner
  won't find them automatically).
- **`--windowed`** suppresses the console window (remove it temporarily
  while debugging a build issue — the console will show you the real
  Python traceback if something breaks).

### 3. If you use `.streamlit/secrets.toml`

Ollama itself needs no secrets (it's local). If you still keep Supabase
credentials in `.streamlit/secrets.toml`, add it to the bundle too:

```powershell
--add-data ".streamlit;.streamlit"
```

### 4. Test it

```powershell
cd dist\NewsAnalyticsAI
NewsAnalyticsAI.exe
```

A native window should open showing the app. First launch may take a few
seconds while Streamlit's server starts in the background.

### 5. (Optional) Wrap it in a proper installer

`dist\NewsAnalyticsAI\` is a folder, not a single installer file. To give
people a normal "Setup.exe" experience with a Start Menu shortcut, use
[Inno Setup](https://jrsoftware.org/isinfo.php) (free) — point it at the
`dist\NewsAnalyticsAI` folder as the source and `NewsAnalyticsAI.exe` as
the main executable, and it'll generate a proper installer.

---

## Troubleshooting

- **Blank/white window on launch**: almost always a missing `--collect-all`.
  Run without `--windowed` to see the real error in the console.
- **"Model not found" errors**: that's Ollama, not the packaging — see the
  Ollama section below.
- **Antivirus flags the .exe**: common false positive with PyInstaller
  builds (the packer pattern looks similar to some malware droppers to
  heuristic scanners). Code-signing the .exe avoids this for wider
  distribution, but isn't needed for personal/internal use.