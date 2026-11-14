# taskbar-radio（工作列音樂播放器）

[English](README.md) ・ **繁體中文**

> 📖 **圖文教學：** https://shao-en.com/blog/taskbar-radio-guide.html ——如果你不知道該如何操作，請把這篇文章交給你的 Claude 或 ChatGPT。

Windows 11 小工具：在工作列時鐘（系統匣）左側放一個音樂播放器，顯示 |◀／播放暫停／▶|、曲名與即時左右聲道波形（兩條灰線重疊）。會把你指定資料夾裡的音檔隨機洗牌播放。可搭配 [taskbar-gauge](https://github.com/shaoen901109/taskbar-gauge)（同一個位置的硬體儀表）一起用。

## 功能

- 上一首、播放／暫停、下一首按鈕，加上曲名與即時波形。左鍵點曲名或波形，或按右鍵，開啟選單。
- 滑鼠停在播放器上滾輪，音量每次 ±5%。
- 支援 `mp3`、`flac`、`wav`、`ogg`（miniaudio 能解的格式），不支援 `m4a`／`aac`。
- 洗牌袋：每個單元都播過一次才重新洗牌，重洗的交界不會連播同一個單元。
- **組曲**：把某個子資料夾勾選為「組曲」，整個資料夾就成為一個單元，裡面的檔案（含子資料夾）依檔名自然排序依序播放；其餘子資料夾（遞迴）與根目錄散檔則是每個檔案一個單元。
- 「上一首」：本曲已播超過 3 秒就重播本曲，否則回到歷史上的上一首。
- 曲名會去掉結尾的 ` [YouTube 11 碼]`；組曲顯示為「資料夾 — 曲名」；曲名太長時以跑馬燈捲動。
- 音訊以串流方式解碼（不整檔載入），很長的檔案也能播；無法解碼的檔案會記錄後自動跳下一首。
- 有全螢幕視窗在前景時自動隱藏；依各螢幕 DPI 縮放；同時只會有一個執行個體。
- 啟動後不會自動播放，要按播放才出聲。

## 需求

- Windows 11（Windows 10 未測試）
- Python 3.10 以上，且 `pythonw` 在 `PATH` 中
- 套件（`requirements.txt`）：`PySide6-Essentials`、`pywin32`、`miniaudio`、`numpy`

## 安裝

```powershell
pip install -r requirements.txt
```

## 使用

雙擊 `啟動.bat`（在背景執行 `pythonw taskbar_player.py`）。預設讀取你的 `%USERPROFILE%\Music` 資料夾，顯示在主螢幕的工作列。

要開機自動啟動，執行 `安裝開機啟動.bat`；它會在你的使用者「啟動」資料夾建立捷徑（不需要系統管理員權限）。`移除開機啟動.bat` 則移除捷徑。也可以從選單勾選切換。

選單項目（左鍵點曲名／波形，或右鍵）：

- **資料夾：…**（顯示目前資料夾）與 **切換資料夾…**：換一個音樂資料夾。
- **組曲**：勾選要當成組曲播放的子資料夾。
- **重新洗牌**：重新洗一次牌。
- **音量**：選擇音量（滾輪也可以調）。
- **開機自動啟動**：切換啟動捷徑。
- **結束**。

資料夾、組曲、音量一變更就會立即寫回 `config.json`。

## 設定

編輯 `taskbar_player.py` 旁邊的 `config.json` 後重新啟動程式。缺少的欄位會用預設值。`root` 可寫 `%USERPROFILE%` 或 `~`。

| 欄位 | 預設 | 說明 |
|---|---|---|
| `root` | `"%USERPROFILE%\\Music"` | 音樂資料夾 |
| `suites` | `[]` | 當成組曲播放的子資料夾 |
| `volume` | `50` | 音量（百分比） |
| `width_dip` | `200` | 播放器寬度（DIP） |
| `pad_dip` | `2` | 工作列高度內的邊距（DIP） |
| `theme` | `"auto"` | 色彩主題 |
| `show_on` | `"primary"` | 顯示在 `all`（全部）、`primary`（主）或 `secondary`（副）工作列 |
| `secondary_right_offset_dip` | `293` | 副工作列：距右緣的偏移（DIP） |
| `primary_tray_gap_dip` | `6` | 主工作列：與系統匣的間距（DIP） |
| `reposition_ms` | `500` | 重新定位／重新置頂的間隔 |
| `hide_when_fullscreen` | `true` | 有全螢幕視窗在前景時隱藏 |
| `hide_scope` | `"any_monitor"` | 全螢幕隱藏的範圍 |
| `marquee_px_per_s` | `6` | 曲名跑馬燈速度（刻意極慢，不搶視覺焦點） |
| `marquee_pause_s` | `5` | 每繞完一圈回到開頭停留的秒數 |

如果你在主工作列也跑 taskbar-gauge，請把 `primary_tray_gap_dip` 調大（例如 174），讓播放器位在儀表左邊。

## 運作原理

Windows 11 沒有 deskband，所以工具為每條工作列開一個透明、不搶焦點、置頂的工具視窗。主工作列依 `Shell_TrayWnd` 內 `TrayNotifyWnd` 的左緣再減 `primary_tray_gap_dip` 定位；副工作列沒有這個子視窗，改用距右緣的固定偏移（`secondary_right_offset_dip`）。位置每 `reposition_ms` 更新一次，以實體像素並依各螢幕 DPI 縮放。音訊用 miniaudio 解碼，經 44.1kHz 立體聲 float32 裝置播放；波形取音量處理前最近 2048 個取樣幀。

## 已知限制

- 不支援 `m4a`／`aac`。
- 暫停時音訊裝置仍開著，只是輸出靜音。
- 換曲時沒有淡入淡出。
- 副工作列偏移是固定值。

## 疑難排解

播放器不見時，看腳本旁的 `error.log`。計時器回呼、繪圖與音訊回呼都包了 try/except，錯誤會寫入記錄（同一個錯誤最多每 60 秒記一次；超過 512 KB 會輪替）。

## 解除安裝

執行 `移除開機啟動.bat` 移除啟動捷徑，從選單選「結束」，再刪除整個資料夾。

## 校驗下載檔

到 [Releases](https://github.com/shaoen901109/taskbar-radio/releases) 下載 `taskbar-radio-v1.0.1.zip` 和 `SHA256SUMS.txt`（版本號以你實際下載的為準）。

1. 用 PowerShell 比對指紋（SHA256，檔案的數位指紋）：

   ```powershell
   Get-FileHash .\taskbar-radio-v1.0.1.zip -Algorithm SHA256
   ```

   輸出的 `Hash` 要和 `SHA256SUMS.txt` 裡的字串一致（大小寫不同沒關係）。

2. 驗證來源（需安裝 [GitHub CLI](https://cli.github.com/)）：

   ```powershell
   gh attestation verify .\taskbar-radio-v1.0.1.zip --repo shaoen901109/taskbar-radio
   ```

   顯示驗證成功，代表這個 zip 是 GitHub Actions 從本 repo 原始碼建出來的，中途沒有被替換。

在 GitHub 上標示 **Verified** 的 commit，代表由作者簽章。

## 技術來源與致謝

| 用途 | 元件 | 授權 |
|---|---|---|
| 介面／繪圖 | [PySide6（Qt for Python）](https://doc.qt.io/qtforpython-6/) | LGPL-3.0／GPL-3.0／商業 |
| 音訊解碼與播放 | [pyminiaudio](https://github.com/irmen/pyminiaudio) | MIT |
| 底層 C 函式庫 | [miniaudio](https://miniaud.io/) | 公有領域或 MIT-0 |
| 波形緩衝 | [numpy](https://numpy.org/) | BSD-3-Clause |
| Windows API 存取 | [pywin32](https://github.com/mhammond/pywin32) | PSF |

本工具在 [Claude Code](https://claude.com/claude-code)（Anthropic）協助下開發。

## 作者

- 網站：https://shaoenstudio.com
- 聯絡信箱：shaoenstudio@gmail.com
- GitHub：[@shaoen901109](https://github.com/shaoen901109)

## 授權

[MIT](LICENSE)
