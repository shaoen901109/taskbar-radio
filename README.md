# taskbar-radio

**English** ・ [繁體中文](README.zh-TW.md)

> 📖 **Step-by-step tutorial (Traditional Chinese):** https://shao-en.com/blog/taskbar-radio-guide.html — not sure how to set it up? Hand the article to Claude or ChatGPT and let it walk you through.

A small Windows 11 music player that lives on the taskbar, just left of the system tray. It shows previous / play-pause / next buttons, the current track title and a live left/right channel waveform (two gray lines drawn on top of each other). It plays the audio files in a folder you choose, in shuffled order. It pairs well with [taskbar-gauge](https://github.com/shaoen901109/taskbar-gauge), which draws hardware gauges in the same spot.

## Features

- Buttons for previous, play/pause and next, plus the track title and a live waveform. Left-click the title or waveform, or right-click, to open the menu.
- Mouse wheel over the player changes the volume in 5% steps.
- Plays `mp3`, `flac`, `wav` and `ogg` (formats miniaudio can decode). `m4a` / `aac` are not supported.
- Shuffle bag: every unit is played once before the bag is reshuffled, and the same unit is never played twice in a row across the reshuffle.
- **Suites**: tick a sub-folder as a "suite" and the whole folder becomes one unit, played in natural file-name order (recursive). Other sub-folders (recursive) and loose files in the root folder are one unit per file.
- "Previous" restarts the current track if it has played for more than 3 seconds, otherwise it goes back to the previous track in history.
- Track titles drop a trailing ` [YouTube 11-char id]`; suites show as "folder — track". Long titles scroll as a marquee.
- Audio is streamed (not loaded whole), so very long files work. Files that cannot be decoded are logged and skipped.
- Hidden while a fullscreen window is in front; per-monitor DPI aware; only one instance runs at a time.
- Playback does not start by itself; press play.

## Requirements

- Windows 11 (Windows 10 is untested)
- Python 3.10+ with `pythonw` on `PATH`
- Packages (`requirements.txt`): `PySide6-Essentials`, `pywin32`, `miniaudio`, `numpy`

## Install

```powershell
pip install -r requirements.txt
```

## Usage

Double-click `啟動.bat` (start; runs `pythonw taskbar_player.py` in the background). By default the player reads your `%USERPROFILE%\Music` folder and shows on the primary taskbar.

To start with Windows, run `安裝開機啟動.bat`; it creates a shortcut in your per-user Startup folder (no administrator rights needed). `移除開機啟動.bat` removes it. You can also toggle this from the menu.

Menu items (left-click the title or waveform, or right-click):

- **Folder: ...** (shows the current folder) and **Switch folder...**: pick another music folder.
- **Suites**: tick the sub-folders that should play as one suite.
- **Reshuffle**: start a fresh shuffle.
- **Volume**: pick a level (the mouse wheel also works).
- **Start with Windows**: toggle the Startup shortcut.
- **Quit**.

The folder, suites and volume are written back to `config.json` as soon as you change them.

## Configuration

Edit `config.json` next to `taskbar_player.py` and restart the program. Missing keys fall back to defaults. `root` accepts `%USERPROFILE%` and `~`.

| Key | Default | Meaning |
|---|---|---|
| `root` | `"%USERPROFILE%\\Music"` | music folder |
| `suites` | `[]` | sub-folders played as suites |
| `volume` | `50` | volume, percent |
| `width_dip` | `200` | player width (DIP) |
| `pad_dip` | `2` | padding inside the taskbar height (DIP) |
| `theme` | `"auto"` | color theme |
| `show_on` | `"primary"` | `all`, `primary` or `secondary` taskbar |
| `secondary_right_offset_dip` | `293` | offset from the right edge on secondary taskbars (DIP) |
| `primary_tray_gap_dip` | `6` | gap to the tray on the primary taskbar (DIP) |
| `reposition_ms` | `500` | reposition / re-topmost interval |
| `hide_when_fullscreen` | `true` | hide while a fullscreen window is in front |
| `hide_scope` | `"any_monitor"` | fullscreen hiding scope |
| `marquee_px_per_s` | `6` | title scroll speed (kept very slow so it doesn't pull your eye) |
| `marquee_pause_s` | `5` | pause at the start of each scroll cycle (seconds) |

If you also run taskbar-gauge on the primary taskbar, raise `primary_tray_gap_dip` (for example 174) so the player sits to the left of the gauges.

## How it works

Windows 11 has no deskband, so the tool opens one transparent, non-focusable, always-on-top tool window per taskbar. On the primary taskbar it is positioned from the left edge of `TrayNotifyWnd` inside `Shell_TrayWnd` minus `primary_tray_gap_dip`; secondary taskbars have no such child window, so a fixed offset from the right edge (`secondary_right_offset_dip`) is used. Position is refreshed every `reposition_ms`, in physical pixels scaled per monitor DPI. Audio is decoded with miniaudio and played through a 44.1 kHz stereo float32 device; the waveform shows the most recent 2048 frames before the volume stage.

## Known limitations

- No `m4a` / `aac` support.
- When paused, the audio device stays open but outputs silence.
- No fade between tracks.
- The secondary-taskbar offset is a fixed value.

## Troubleshooting

If the player disappears, look at `error.log` next to the script. Timer callbacks, painting and the audio callback are wrapped in try/except; errors are logged (the same error at most once per 60 seconds; the log rotates above 512 KB).

## Uninstall

Run `移除開機啟動.bat` to remove the startup shortcut, choose Quit from the menu, then delete the folder.

## Verify your download

Download `taskbar-radio-v1.0.0.zip` and `SHA256SUMS.txt` from [Releases](https://github.com/shaoen901109/taskbar-radio/releases) (use the version you actually downloaded).

1. Compare the checksum in PowerShell:

   ```powershell
   Get-FileHash .\taskbar-radio-v1.0.0.zip -Algorithm SHA256
   ```

   The `Hash` must match the string in `SHA256SUMS.txt` (letter case does not matter).

2. Verify where it was built (needs [GitHub CLI](https://cli.github.com/)):

   ```powershell
   gh attestation verify .\taskbar-radio-v1.0.0.zip --repo shaoen901109/taskbar-radio
   ```

   A successful result means GitHub Actions built this zip from this repository's source and it was not swapped along the way.

Commits marked **Verified** on GitHub are signed by the author.

## Credits

| Purpose | Component | License |
|---|---|---|
| GUI / drawing | [PySide6 (Qt for Python)](https://doc.qt.io/qtforpython-6/) | LGPL-3.0 / GPL-3.0 / commercial |
| Audio decoding and playback | [pyminiaudio](https://github.com/irmen/pyminiaudio) | MIT |
| Underlying C library | [miniaudio](https://miniaud.io/) | Public domain or MIT-0 |
| Waveform buffers | [numpy](https://numpy.org/) | BSD-3-Clause |
| Windows API access | [pywin32](https://github.com/mhammond/pywin32) | PSF |

Developed with the help of [Claude Code](https://claude.com/claude-code) (Anthropic).

## Author

- Website: https://shaoenstudio.com
- Email: shaoenstudio@gmail.com
- GitHub: [@shaoen901109](https://github.com/shaoen901109)

## License

[MIT](LICENSE)
