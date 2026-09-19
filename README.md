# PageTurner - PDF & EPUB reader for Windows 11

A lightweight reader built on Qt (PySide6) and MuPDF. Opens PDF, EPUB, MOBI, FB2, XPS and CBZ.

## Features
- Remembers where you stopped in every book, and reopens the last book on launch
- Contents panel (table of contents) with clickable chapters
- Fit width / fit page / custom zoom, Ctrl + mouse wheel zoom
- Adjustable text size for EPUB (reflows the book and keeps your place)
- Search with highlighted matches (Enter / F3 / Shift+F3)
- Clickable links: web links open in your browser, links inside the book jump to the target
  (including EPUB "Click here to view code image" links); Alt+Left or Backspace goes back
- Themes: Light, Sepia and Night (Ctrl+D toggles night)
- Two-page view, like an open book (Ctrl+2)
- EPUB books fill the window like an e-reader, with your choice of font, text size,
  line spacing, margins and justified text (Reading settings, Ctrl+,)
- Chapter name and a reading-progress bar in the status bar
- Next pages are rendered ahead of time, so turning pages feels instant
- **Digital signature verification** like Acrobat: a coloured bar says whether signatures are
  valid, and the Signature panel (Ctrl+Shift+S) shows who signed, when, whether the document was
  changed afterwards, and the certificate. Click a signature on the page to see its details.
- Password-protected PDFs (you're asked for the password; signatures are checked too)
- Starts on a clean welcome screen with your recent files
- Full screen, drag-and-drop, recent files, password-protected PDFs
- Sharp rendering on high-DPI / scaled displays

## Files
- `pageturner.py` - the app
- `assets/` - logo (SVG source, PNG, and Windows .ico)
- `installer/` - installer script (Inno Setup) and the exe's version details
- `build_installer.bat` - builds the app and the installer in one go

## Install it like a normal Windows program (recommended)
1. Install Python 3.10+ from python.org (tick "Add Python to PATH").
2. Double-click `build_installer.bat`. It builds the app and creates
   `installer\Output\PageTurner-Setup-1.1.0.exe` (it installs Inno Setup via winget if needed).
3. Run `PageTurner-Setup-1.1.0.exe`. You can now delete this source folder - the app lives in
   Program Files like any other program.

The installer gives you:
- PageTurner in the Start menu (optional desktop shortcut)
- **Right-click a PDF/EPUB/MOBI/FB2/XPS/CBZ -> Open with PageTurner**
  (on Windows 11 it's under "Show more options"; PageTurner also appears in the
  "Open with" submenu of the new menu)
- PageTurner listed in Settings -> Apps -> Default apps, so you can make it the default reader
- A proper uninstaller in Settings -> Apps -> Installed apps

Windows may show "Windows protected your PC" the first time you run the installer because it
isn't code-signed. Click "More info" -> "Run anyway".

To release an update: change the version in `pageturner.py` (APP_VERSION),
`installer\PageTurner.iss` and `installer\version_info.txt`, rebuild, and run the new
installer - it upgrades the existing install in place.

## Run it without installing (needs Python 3.10+ from python.org or the Microsoft Store)
Double-click `run.bat`, or:
```
pip install -r requirements.txt
python pageturner.py
```

## Make a real .exe
Double-click `build.bat`. The app lands in `dist\PageTurner\` - copy that whole folder
anywhere (e.g. `C:\Apps\PageTurner`) and pin `PageTurner.exe` to Start or the taskbar.
For a single-file exe, add `--onefile` to the PyInstaller line (starts a bit slower).

## Make it the default app for PDFs/EPUBs
Right-click any .epub or .pdf -> Open with -> Choose another app -> Choose an app on your PC
-> pick `PageTurner.exe` -> click "Always".

## Shortcuts
Press F1 in the app for the full list.

## About signature trust
A signature is shown as **valid** when the document is unchanged since signing *and* the signer's
certificate chains up to a certificate you trust. PageTurner trusts the certificates in the
Windows trusted root store, plus any you add yourself. If a signature shows as "identity
unknown" (common for Indian DSC / e-Sign certificates issued under CCA India, which Acrobat
trusts via Adobe's own list), either:
- open the signature's **Certificate details** and click **Trust this certificate**, or
- use **Signatures > Import trusted certificate** to add the issuing CA's root certificate
  (e.g. the CCA India root from https://cca.gov.in), which then covers every signature it issued.

Certificates are also checked for revocation online when the certificate provides that
information, so the first check of a document can take a few seconds.
