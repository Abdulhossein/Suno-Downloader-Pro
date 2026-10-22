# Suno Downloader Pro 🎵

A powerful, cross-platform (Desktop + Android/Pydroid) GUI downloader for [Suno](https://suno.com) music. Download high-quality audio, lyrics, and cover art — with automatic DRM/encryption handling, cookie-based authentication, and MP3 conversion.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.5%2B-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20Android-lightgrey)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## ✨ Features

- 🎨 **Modern Dark UI** — Mobile-friendly, touch-optimized Qt interface with smooth scrolling
- 🔓 **Automatic Decryption** — Handles Suno's "Mango" DRM (AES-GCM key unwrap + AES-CTR stream decryption) transparently
- 🍪 **Cookie-based Auth** — Uses your Suno session cookie; auto-refreshes short-lived JWTs via `__client` token
- 🎵 **Multiple Output Options** — Audio, lyrics (`.txt`), and cover art (`.jpg`)
- 🔄 **Smart Fallback** — Tries multiple audio URL candidates (API media_urls → og:audio → CDN scan → legacy endpoints)
- ⚡ **Resume Support** — Interrupted downloads resume from `.part` files
- 🎼 **MP3 Conversion** — Automatically converts M4A/Opus to MP3 with `ffmpeg` (optional)
- 📱 **Android Ready** — Works under Pydroid 3 with proper storage permissions
- 🗂️ **Deduplication** — Multiple links pointing to the same song are downloaded once
- 💾 **Live Storage Meter** — See free/used space before choosing a save folder

---

## 📸 Screenshots

> *(Add your own screenshots here — 440×780 is the recommended window size)*

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/suno-downloader-pro.git
cd suno-downloader-pro
```

### 2. Install Python dependencies

```bash
pip install PySide6 requests beautifulsoup4 cryptography
```

### 3. *(Optional)* Install ffmpeg for MP3 conversion

**Option A — Python package (easiest, works on Android too):**
```bash
pip install imageio-ffmpeg
```

**Option B — System ffmpeg:**
- **Windows:** `winget install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html)
- **Linux:** `sudo apt install ffmpeg`
- **macOS:** `brew install ffmpeg`
- **Termux (Android):** `pkg install ffmpeg`

### 4. Run the app

```bash
python sunoDownloader.py
```

---

## 🍪 Getting Your Cookie (Required for Private/Auth Content)

Suno's public tracks can sometimes be downloaded without a cookie, but **authenticated cookies are strongly recommended** for reliable access to your own generated songs, higher-quality streams, and for DRM decryption.

### Recommended Method — Browser Extension

1. Install the **"Get cookies.txt LOCALLY"** extension:
   👉 https://chromewebstore.google.com/detail/gdbmkehljhmfcjgbjcfaklnabeccddna

2. Log in to [suno.com](https://suno.com) in that same browser.

3. Click the extension icon → **Export** → save the file as `cookie.txt` **in the same folder as `sunoDownloader.py`**.

4. Launch the app. It will auto-detect and load `cookie.txt`.

> ⚠️ **Security note:** Your cookie grants full access to your Suno account. Never commit `cookie.txt` to a public repo (a `.gitignore` entry is included).

### Alternative — Manual export

1. Open DevTools (`F12`) on suno.com.
2. Go to **Application → Cookies → https://suno.com**.
3. Copy the values of `__client` (and optionally `__session`).
4. Save the JSON array format your script expects into `cookie.txt`.

---

## 🎯 Usage

1. **Paste links** into the URL field — any of these work:
   - `https://suno.com/s/XXXXXXXXXXXX` (share links)
   - `https://suno.com/song/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
   - A bare UUID: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

2. **Choose a save folder** — tap **📂 Choose Folder** (Android users get quick shortcuts to `/Download/Suno`, `/Music`, etc.)

3. **Select what to download** — Audio ✅ / Lyrics ✅ / Cover ⬜

4. **Configure options:**
   - **Skip Existing** — don't re-download already-valid files
   - **Convert to MP3** — requires ffmpeg (auto-detected)

5. Hit **🚀 Start Download** and watch the log for progress.

Files are organized as:
```
<save_dir>/
├── Song Title_abcd1234.mp3
├── Lyrics/
│   └── Song Title_abcd1234_lyrics.txt
└── Covers/
    └── Song Title_abcd1234.jpg
```

---

## 🔐 How Authentication Works

This tool does **not** store your email/password. Instead it uses Suno's own Clerk-based session:

1. Loads `__client` cookie from `cookie.txt`.
2. Exchanges it at `https://auth.suno.com/v1/client/sessions/{id}/tokens` for a short-lived JWT.
3. Attaches that JWT as `Authorization: Bearer ...` to Suno API calls.
4. Auto-refreshes it when expired — **you only log in once**, the cookie stays valid for weeks.

---

## 🧩 How Decryption Works

Suno streams audio encrypted with a two-layer scheme:

1. The CDN serves an **AES-CTR** encrypted `.m4a`.
2. The player fetches a short-lived DRM license from `/api/mango/rights` containing:
   - A wrapped CTR **key** and **IV** (each AES-GCM encrypted).
   - A `glt` seed used to derive the unwrap key via `SHA-256`.
3. The player unwraps the key/IV with **AES-GCM**, then decrypts the stream with **AES-CTR**.

This script implements that exact flow (`fetch_stream_rights()` → `decrypt_stream()`), so downloaded files play natively in any media player.

---

## 📱 Android / Pydroid 3 Notes

- The GUI automatically resizes for phones and enables touch scrolling.
- Default save directory: `/storage/emulated/0/Download/Suno`.
- If permissions fail, use **📂 Choose Folder** → **📥 Download**.
- For MP3 conversion: `pip install imageio-ffmpeg` inside Pydroid.

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---|---|
| **`playwright: not recognized`** | Use `python -m playwright install firefox` instead |
| **`cryptography` missing** | `pip install cryptography` |
| **Decryption fails** | Verify `cookie.txt` is fresh; the `__client` cookie may have expired |
| **403 on download** | Session cookie invalid — re-export cookies from the browser |
| **No audio URL found** | The clip may be deleted or region-locked |
| **MP3 conversion fails** | Ensure ffmpeg is on PATH or install `imageio-ffmpeg` |
| **`__session` expired warning** | Normal — the app auto-refreshes via `__client` |
| **App crashes on startup** | Ensure PySide6 ≥ 6.5: `pip install -U PySide6` |

---

## 📁 Project Structure

```
suno-downloader-pro/
├── sunoDownloader.py     # Main application (GUI + downloader)
├── cookie.txt            # Your cookies (NOT committed — see .gitignore)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 📦 requirements.txt

```
PySide6>=6.5.0
requests>=2.31.0
beautifulsoup4>=4.12.0
cryptography>=41.0.0
imageio-ffmpeg>=0.4.9   # optional — for MP3 conversion
```

---

## ⚖️ Legal & Disclaimer

This tool is provided for **personal use only** — to download music you have legitimately generated or that is publicly shared on Suno. You are responsible for complying with:

- [Suno's Terms of Service](https://suno.com/terms)
- Your local copyright laws

The authors of this project are **not affiliated with Suno AI** and take no responsibility for misuse.

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you'd like to change.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m "Add amazing feature"`
4. Push: `git push origin feature/amazing-feature`
5. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [Suno AI](https://suno.com) — for the incredible music generation platform
- [PySide6](https://pypi.org/project/PySide6/) — Qt bindings
- [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/gdbmkehljhmfcjgbjcfaklnabeccddna) — simplest way to export cookies
- [Playwright](https://playwright.dev/python/) — used for the optional semi-automated login flow

---

## ⭐ Support

If this project saved you some time, please consider giving it a star ⭐ — it helps others discover the project!

**Made with ❤️ for the Suno community.**
