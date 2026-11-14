"""工作列音樂播放器：在副螢幕工作列顯示 上一首／播放／下一首＋曲名＋即時左右聲道波形。"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

import numpy as np
import win32api
import win32con
import win32event
import win32gui
import winerror

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QEvent
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont, QFontMetricsF, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QToolTip, QFileDialog

import library as lib

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")
LOG_PATH = os.path.join(HERE, "error.log")
LNK_NAME = "工作列音樂播放器.lnk"
# 副工作列右緣偏移 = 儀表右緣偏移 125 + 儀表寬 (3*44 + 2*12 = 156，以 48dip 工作列計) + 間距 12
DEFAULT_CFG = {
    "root": os.path.join(os.path.expanduser("~"), "Music"), "suites": [], "volume": 50,
    "width_dip": 200, "pad_dip": 2, "theme": "auto", "show_on": "primary",
    "secondary_right_offset_dip": 293, "primary_tray_gap_dip": 6,
    "reposition_ms": 500, "hide_when_fullscreen": True, "hide_scope": "any_monitor",
    "marquee_px_per_s": 6, "marquee_pause_s": 5,
}


def load_cfg():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as ex:
        cfg["_load_error"] = f"config.json 讀取失敗，改用預設值：{ex}"
    cfg["root"] = os.path.expandvars(os.path.expanduser(cfg["root"]))  # 支援 %USERPROFILE%／~
    return cfg


CFG = load_cfg()
_PERSIST = ("root", "suites", "volume")


def save_cfg():
    try:
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                disk = json.load(f)
        except Exception:
            disk = dict(DEFAULT_CFG)
        disk.update({k: CFG[k] for k in _PERSIST})
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(disk, f, ensure_ascii=False, indent=2)
    except Exception:
        log_error("save_cfg")


# ---------- 錯誤記錄 ----------
_last_err = {}


def log_error(where):
    """寫入 error.log；同一處的同一錯誤 60 秒內只記一次，超過 512KB 輪替。"""
    import traceback
    tb = traceback.format_exc()
    key = (where, tb.strip().splitlines()[-1] if tb.strip() else "")
    now = time.time()
    if now - _last_err.get(key, 0) < 60:
        return
    _last_err[key] = now
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 512 * 1024:
            os.replace(LOG_PATH, LOG_PATH + ".old")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} [{where}]\n{tb}\n")
    except Exception:
        pass


def log_msg(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def guarded(fn, where):
    def wrapper(*a):
        try:
            fn(*a)
        except Exception:
            log_error(where)
    return wrapper


# ---------- Win32 輔助（同硬體儀表） ----------
user32 = ctypes.windll.user32
shcore = ctypes.windll.shcore
user32.MonitorFromPoint.restype = wintypes.HMONITOR
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]


def monitor_dpi(hmon):
    d, e = ctypes.c_uint(96), ctypes.c_uint(96)
    try:
        shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(d), ctypes.byref(e))
    except Exception:
        pass
    return d.value or 96


def find_taskbars():
    """回傳 [(hwnd, rect, hmon, tray_left或None, is_primary)]"""
    res = []

    def cb(h, _):
        try:
            cls = win32gui.GetClassName(h)
        except Exception:
            return True
        if cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd") and win32gui.IsWindowVisible(h):
            r = win32gui.GetWindowRect(h)
            pt = wintypes.POINT((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            hmon = user32.MonitorFromPoint(pt, 2)
            tray_left = None
            try:
                tn = win32gui.FindWindowEx(h, 0, "TrayNotifyWnd", None)
                if tn and win32gui.IsWindowVisible(tn):
                    tr = win32gui.GetWindowRect(tn)
                    if tr[2] - tr[0] > 20:
                        tray_left = tr[0]
            except Exception:
                pass
            res.append((h, r, hmon, tray_left, cls == "Shell_TrayWnd"))
        return True

    win32gui.EnumWindows(cb, None)
    return res


DESKTOP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def fullscreen_monitor():
    try:
        fg = win32gui.GetForegroundWindow()
        if not fg or not win32gui.IsWindowVisible(fg):
            return None
        if win32gui.GetClassName(fg) in DESKTOP_CLASSES or win32gui.IsIconic(fg):
            return None
        r = win32gui.GetWindowRect(fg)
        hmon = user32.MonitorFromWindow(fg, 2)
        m = win32api.GetMonitorInfo(hmon)["Monitor"]
        if r[0] <= m[0] and r[1] <= m[1] and r[2] >= m[2] and r[3] >= m[3]:
            return int(hmon)
    except Exception:
        pass
    return None


def light_theme():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(k, "SystemUsesLightTheme")[0] == 1
    except Exception:
        return False


# ---------- 開機啟動捷徑 ----------
def startup_lnk():
    return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup", LNK_NAME)


def autostart_enabled():
    return os.path.exists(startup_lnk())


def set_autostart(on):
    if not on:
        try:
            os.remove(startup_lnk())
        except FileNotFoundError:
            pass
        return
    exe = sys.executable
    pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    env = dict(os.environ, LNK=startup_lnk(), TGT=pw if os.path.exists(pw) else exe, DIR=HERE)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
          "$s.TargetPath=$env:TGT;$s.Arguments='taskbar_player.py';$s.WorkingDirectory=$env:DIR;$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True,
                   creationflags=0x08000000, timeout=30)


# ---------- 音訊引擎 ----------
RATE = 44100
RING = 2048


class Engine:
    """miniaudio 串流解碼（不整檔載入）→ PlaybackDevice；波形取自音量前的最近 2048 幀。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.src = None
        self.buf = np.zeros((0, 2), np.float32)
        self.playing = False
        self.volume = 0.5
        self.ended = False
        self.failed = False
        self.frames = 0
        self.ring = np.zeros((RING, 2), np.float32)
        self.dev = None
        self.path = None

    def _ensure_dev(self):
        if self.dev is None:
            import miniaudio
            self.dev = miniaudio.PlaybackDevice(
                output_format=miniaudio.SampleFormat.FLOAT32, nchannels=2,
                sample_rate=RATE, buffersize_msec=120)
            g = self._cb()
            next(g)
            self.dev.start(g)

    def _cb(self):
        n = yield b""
        while True:
            try:
                out = self._fill(n)
            except Exception:
                log_error("audio_callback")
                out = np.zeros((n, 2), np.float32)
            n = yield out.tobytes()

    def _fill(self, n):
        with self.lock:
            if not self.playing or (self.src is None and len(self.buf) == 0):
                take = np.zeros((n, 2), np.float32)
            else:
                while len(self.buf) < n and self.src is not None:
                    try:
                        c = np.frombuffer(next(self.src), dtype=np.float32).reshape(-1, 2)
                        self.buf = np.concatenate((self.buf, c)) if len(self.buf) else c
                    except StopIteration:
                        self.src = None
                    except Exception:
                        log_error("decode")
                        self.src = None
                        self.buf = np.zeros((0, 2), np.float32)
                        self.failed = True
                take = self.buf[:n]
                self.buf = self.buf[n:]
                self.frames += len(take)
                if len(take) < n:
                    take = np.concatenate((take, np.zeros((n - len(take), 2), np.float32)))
                if self.src is None and len(self.buf) == 0 and not self.failed:
                    self.ended = True
            m = min(n, RING)
            self.ring = np.concatenate((self.ring[m:], take[-m:]))
            return take * self.volume

    def load(self, path):
        """開檔（失敗丟例外）並立刻開始播放。"""
        import miniaudio
        src = miniaudio.stream_file(path, output_format=miniaudio.SampleFormat.FLOAT32,
                                    nchannels=2, sample_rate=RATE, frames_to_read=RING)
        first = np.frombuffer(next(src), dtype=np.float32).reshape(-1, 2)
        with self.lock:
            self.src, self.buf, self.path = src, first.copy(), path
            self.frames, self.ended, self.failed = 0, False, False
            self.playing = True
        self._ensure_dev()

    def pause(self):
        with self.lock:
            self.playing = False

    def resume(self):
        if self.src is not None or len(self.buf):
            self._ensure_dev()
            with self.lock:
                self.playing = True

    def position_s(self):
        return self.frames / RATE

    def wave(self, n):
        """回傳 (L, R) 各 n 點，值域 -1..1；每段取絕對值最大的樣本以保留尖峰。"""
        with self.lock:
            r = self.ring.copy()
        blk = max(1, RING // max(n, 1))
        k = (len(r) // blk) * blk
        r = r[len(r) - k:].reshape(-1, blk, 2)
        idx = np.abs(r).argmax(axis=1)
        out = np.take_along_axis(r, idx[:, None, :], axis=1)[:, 0, :]
        return out[:, 0], out[:, 1]

    def close(self):
        try:
            if self.dev:
                self.dev.close()
        except Exception:
            pass


# ---------- 控制器 ----------
class Controller:
    def __init__(self):
        self.engine = Engine()
        self.engine.volume = CFG["volume"] / 100.0
        self.playlist = lib.Playlist()
        self.title = ""
        self.folder = ""
        self.missing = False
        self.fail_streak = 0
        self.rescan()

    # 狀態
    @property
    def playing(self):
        return self.engine.playing

    def rescan(self):
        units = lib.scan(CFG["root"], CFG["suites"])
        self.missing = units is None
        self.playlist.set_units(units or [])
        if self.missing:
            self.title, self.folder = "找不到資料夾", CFG["root"]
        elif not self.title or self.title == "找不到資料夾":
            self.title, self.folder = ("資料夾內沒有音樂" if not units else "按播放開始"), CFG["root"]

    def subfolders(self):
        try:
            return sorted((d for d in os.listdir(CFG["root"]) if os.path.isdir(os.path.join(CFG["root"], d))),
                          key=lib.natural_key)
        except OSError:
            return []

    def _play(self, item):
        """item=(unit, idx, path) 或 None；失敗就記錄並跳下一首。"""
        n_units = max(1, len(self.playlist.units))
        while item is not None:
            unit, idx, path = item
            try:
                self.engine.load(path)
                self.title = lib.track_title(path, unit)
                self.folder = unit.folder
                self.fail_streak = 0
                return
            except Exception:
                log_error("load:" + os.path.basename(path))
                self.fail_streak += 1
                if self.fail_streak > n_units + 5:
                    break
                item = self.playlist.next()
        self.engine.pause()
        self.title = "沒有可播放的音樂"

    def toggle(self):
        e = self.engine
        if e.playing:
            e.pause()
        elif e.path is not None and not e.ended and (e.src is not None or len(e.buf)):
            e.resume()
        else:
            self.rescan()
            self._play(self.playlist.next())

    def next(self):
        self._play(self.playlist.next())

    def prev(self):
        self._play(self.playlist.prev(self.engine.position_s()))

    def poll(self):
        if self.engine.ended or self.engine.failed:
            if self.engine.failed:
                log_msg("解碼失敗，跳過：" + str(self.engine.path))
                self.fail_streak += 1
            self.engine.ended = self.engine.failed = False
            if self.fail_streak > len(self.playlist.units) + 5:
                self.engine.pause()
                return
            self.next()

    def set_root(self, root):
        CFG["root"] = root
        CFG["suites"] = []
        save_cfg()
        self.playlist = lib.Playlist()
        self.rescan()

    def toggle_suite(self, name, on):
        s = set(CFG["suites"])
        (s.add if on else s.discard)(name)
        CFG["suites"] = sorted(s, key=lib.natural_key)
        save_cfg()
        self.playlist.reshuffle()
        self.rescan()

    def reshuffle(self):
        self.playlist.reshuffle()

    def set_volume(self, pct):
        pct = max(0, min(100, int(pct)))
        CFG["volume"] = pct
        self.engine.volume = pct / 100.0
        save_cfg()


# ---------- 視窗 ----------
class PlayerBar(QWidget):
    def __init__(self, ctl):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setMouseTracking(True)
        self.ctl = ctl
        self.light = False
        self.k = 1.0
        self.last_geom = None
        self.hover = None
        self.offset = 0.0
        self._t = time.time()
        self.vol_tip_until = 0
        self.setWindowTitle("工作列音樂播放器")
        h = int(self.winId())
        ex = win32gui.GetWindowLong(h, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(h, win32con.GWL_EXSTYLE, ex | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW)
        self.timer = QTimer(self)
        self.timer.timeout.connect(guarded(self.tick, "tick"))

    # 計時器只在顯示時跑
    def showEvent(self, e):
        self._t = time.time()
        self.timer.start(33)
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def layout_rects(self):
        k, h = self.k, self.height()
        cy = h / 2
        cells = [("prev", 4 * k, 24 * k), ("play", 28 * k, 32 * k), ("next", 60 * k, 24 * k)]
        icons = {n: QRectF(x, cy - 16 * k, w, 32 * k) for n, x, w in cells}
        text = QRectF(88 * k, 0, self.width() - 88 * k - 4 * k, h)
        return icons, text

    def text_font(self):
        f = QFont("Microsoft JhengHei UI")
        f.setPixelSize(max(9, int(round(self.height() * 0.30))))
        return f

    def tick(self):
        now = time.time()
        dt, self._t = now - self._t, now
        icons, text = self.layout_rects()
        tw = QFontMetricsF(self.text_font()).horizontalAdvance(self.ctl.title)
        over = tw > text.width()
        if over:
            loop = tw + 40 * self.k
            if now >= getattr(self, "_hold_until", 0):
                new = (self.offset + CFG["marquee_px_per_s"] * self.k * dt) % loop
                if new < self.offset:   # 繞完一圈：回到開頭停一下再走，降低存在感
                    new, self._hold_until = 0.0, now + CFG["marquee_pause_s"]
                self.offset = new
        else:
            self.offset = 0.0
        if self.ctl.playing or over or self.ctl.engine.playing != getattr(self, "_was", None):
            self._was = self.ctl.engine.playing
            self.update()

    def paintEvent(self, e):
        try:
            self._paint()
        except Exception:
            log_error("paint")

    def _paint(self):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        k, h = self.k, self.height()
        fg = QColor(30, 30, 30) if self.light else QColor(245, 245, 245)
        dim = QColor(120, 120, 120) if self.light else QColor(150, 150, 155)
        icons, text = self.layout_rects()
        playing = self.ctl.playing
        # 圖示
        for name, r in icons.items():
            if self.hover == name:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 0, 0, 30) if self.light else QColor(255, 255, 255, 30))
                p.drawRoundedRect(r, 6 * k, 6 * k)
            c = fg if name == "play" else dim
            p.setPen(QPen(c, 2 * k, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(c)
            cx, cy = r.center().x(), r.center().y()
            if name == "play":
                if playing:
                    for dx in (-5.5, 1.5):
                        p.drawRoundedRect(QRectF(cx + dx * k, cy - 8 * k, 4 * k, 16 * k), 1.5 * k, 1.5 * k)
                else:
                    s = 9 * k
                    p.drawPolygon(QPolygonF([QPointF(cx - s * 0.6, cy - s), QPointF(cx - s * 0.6, cy + s),
                                             QPointF(cx + s, cy)]))
            else:
                s = 6 * k
                d = -1 if name == "prev" else 1   # prev：|◀  next：▶|
                bar_x = cx - d * s * 1.0
                tri_tip = cx + d * s * -0.9 if name == "prev" else cx + d * s * 1.0
                if name == "prev":
                    p.drawRoundedRect(QRectF(cx - s * 1.0 - 1 * k, cy - s, 2 * k, 2 * s), k, k)
                    p.drawPolygon(QPolygonF([QPointF(cx - s * 0.5, cy), QPointF(cx + s * 1.0, cy - s),
                                             QPointF(cx + s * 1.0, cy + s)]))
                else:
                    p.drawRoundedRect(QRectF(cx + s * 1.0 - 1 * k, cy - s, 2 * k, 2 * s), k, k)
                    p.drawPolygon(QPolygonF([QPointF(cx + s * 0.5, cy), QPointF(cx - s * 1.0, cy - s),
                                             QPointF(cx - s * 1.0, cy + s)]))
        # 標題（超寬跑馬燈）
        f = self.text_font()
        fm = QFontMetricsF(f)
        title = self.ctl.title
        tw = fm.horizontalAdvance(title)
        title_h = h * 0.50
        p.save()
        p.setClipRect(QRectF(text.x(), 0, text.width(), title_h + 2 * k))
        p.setFont(f)
        p.setPen(fg)
        base = title_h / 2 + (fm.ascent() - fm.descent()) / 2 + 1 * k
        if tw > text.width():
            loop = tw + 40 * k
            x = text.x() - self.offset
            p.drawText(QPointF(x, base), title)
            p.drawText(QPointF(x + loop, base), title)
        else:
            p.drawText(QPointF(text.x(), base), title)
        p.restore()
        # 波形：左右聲道兩條灰線重疊
        wy0, wy1 = title_h + 3 * k, h - 3 * k
        wc, wh = (wy0 + wy1) / 2, (wy1 - wy0) / 2
        n = max(8, int(text.width() / max(1.0, 2 * k)))
        if playing:
            L, R = self.ctl.engine.wave(n)
        else:
            L = R = np.zeros(n, np.float32)
        gain = 1.8
        xs = np.linspace(text.x(), text.right(), len(L))
        for ch, col in ((R, QColor(130, 130, 135, 200) if not self.light else QColor(110, 110, 115, 200)),
                        (L, QColor(190, 190, 195, 220) if not self.light else QColor(60, 60, 65, 220))):
            path = QPainterPath()
            for i, (x, v) in enumerate(zip(xs, ch)):
                y = wc - max(-1.0, min(1.0, float(v) * gain)) * wh
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(col, 1.2 * k, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        p.end()

    # 互動
    def hit(self, pos):
        icons, text = self.layout_rects()
        for n, r in icons.items():
            if r.contains(pos):
                return n
        return "text" if text.contains(pos) else None

    def mouseMoveEvent(self, e):
        h = self.hit(e.position())
        h = h if h != "text" else None
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self.hit(e.position())
        pos = e.globalPosition().toPoint()
        if h == "play":
            self.ctl.toggle()
        elif h == "prev":
            self.ctl.prev()
        elif h == "next":
            self.ctl.next()
        elif h == "text":
            self.show_menu(pos)
        self.update()

    def contextMenuEvent(self, e):
        self.show_menu(e.globalPos())

    def wheelEvent(self, e):
        step = 5 if e.angleDelta().y() > 0 else -5
        self.ctl.set_volume(CFG["volume"] + step)
        QToolTip.showText(e.globalPosition().toPoint(), f"音量 {CFG['volume']}%", self)
        e.accept()

    def event(self, e):
        if e.type() == QEvent.ToolTip:
            QToolTip.showText(e.globalPos(), f"{self.ctl.title}\n資料夾：{self.ctl.folder}\n音量 {CFG['volume']}%", self)
            return True
        return super().event(e)

    def show_menu(self, pos):
        ctl = self.ctl
        ctl.rescan()
        m = QMenu(self)
        hdr = m.addAction(f"資料夾：{CFG['root']}")
        hdr.setEnabled(False)
        m.addAction("切換資料夾…").triggered.connect(lambda: QTimer.singleShot(0, self.choose_root))
        sm = m.addMenu("組曲（勾選＝整個資料夾依序播放）")
        subs = ctl.subfolders()
        if not subs:
            sm.addAction("（沒有子資料夾）").setEnabled(False)
        for name in subs:
            a = sm.addAction(name)
            a.setCheckable(True)
            a.setChecked(name in CFG["suites"])
            a.toggled.connect(lambda on, n=name: ctl.toggle_suite(n, on))
        m.addAction("重新洗牌").triggered.connect(ctl.reshuffle)
        vm = m.addMenu("音量")
        for v in (25, 50, 75, 100):
            a = vm.addAction(f"{v}%")
            a.setCheckable(True)
            a.setChecked(CFG["volume"] == v)
            a.triggered.connect(lambda _=False, v=v: ctl.set_volume(v))
        m.addSeparator()
        au = m.addAction("開機自動啟動")
        au.setCheckable(True)
        au.setChecked(autostart_enabled())
        au.toggled.connect(guarded(set_autostart, "autostart"))
        m.addAction("結束").triggered.connect(QApplication.quit)
        m.exec(pos)

    def choose_root(self):
        d = QFileDialog.getExistingDirectory(None, "選擇音樂資料夾", CFG["root"] if os.path.isdir(CFG["root"]) else "")
        if d:
            self.ctl.set_root(os.path.normpath(d))

    def place(self, x, y, w, h):
        g = (x, y, w, h)
        if g != self.last_geom:
            self.last_geom = g
            win32gui.SetWindowPos(int(self.winId()), win32con.HWND_TOPMOST, x, y, w, h,
                                  win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)
        else:
            win32gui.SetWindowPos(int(self.winId()), win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOACTIVATE | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)


class Manager:
    def __init__(self, app):
        self.ctl = Controller()
        self.bars = {}
        self.light = light_theme() if CFG["theme"] == "auto" else CFG["theme"] == "light"
        self.t_poll = QTimer()
        self.t_poll.timeout.connect(guarded(self.poll, "poll"))
        self.t_poll.start(200)
        self.t_pos = QTimer()
        self.t_pos.timeout.connect(guarded(self.reposition, "reposition"))
        self.t_pos.start(CFG["reposition_ms"])
        self._n = 0
        guarded(self.reposition, "reposition")()
        app.aboutToQuit.connect(self.ctl.engine.close)

    def poll(self):
        self.ctl.poll()
        self._n += 1
        if CFG["theme"] == "auto" and self._n % 5 == 0:
            self.light = light_theme()
            for b in self.bars.values():
                b.light = self.light

    def reposition(self):
        tbs = find_taskbars()
        fs = fullscreen_monitor() if CFG["hide_when_fullscreen"] else None
        alive = set()
        show_on = CFG["show_on"]
        for hwnd, r, hmon, tray_left, primary in tbs:
            if (show_on == "primary" and not primary) or (show_on == "secondary" and primary):
                continue
            alive.add(hwnd)
            k = monitor_dpi(hmon) / 96.0
            pad = int(round(CFG["pad_dip"] * k))
            h = (r[3] - r[1]) - 2 * pad
            w = int(round(CFG["width_dip"] * k))
            if tray_left is not None and primary:
                right = tray_left - int(round(CFG["primary_tray_gap_dip"] * k))
            else:
                right = r[2] - int(round(CFG["secondary_right_offset_dip"] * k))
            bar = self.bars.get(hwnd)
            if bar is None:
                bar = PlayerBar(self.ctl)
                bar.light = self.light
                self.bars[hwnd] = bar
            bar.k = k
            hide = fs is not None and (CFG["hide_scope"] != "same_monitor" or int(hmon) == fs)
            if hide:
                if bar.isVisible():
                    bar.hide()
                    bar.last_geom = None
                continue
            if not bar.isVisible():
                bar.show()
                bar.last_geom = None
            bar.place(right - w, r[1] + pad, w, h)
        for hwnd in list(self.bars):
            if hwnd not in alive:
                self.bars.pop(hwnd).close()


# ---------- 自我測試：--selftest <png>（音量 0，不出聲） ----------
def run_selftest(mgr, png):
    ctl = mgr.ctl
    ctl.engine.volume = 0.0   # 不經 set_volume，不寫入 config

    def start():
        ctl.toggle()

    def shot():
        from PIL import ImageGrab
        info = []
        for b in mgr.bars.values():
            if b.isVisible():
                g = b.last_geom
                info.append(g)
        tb = [t for t in find_taskbars() if t[0] in mgr.bars]
        r = tb[0][1] if tb else (0, 0, 800, 48)
        img = ImageGrab.grab(bbox=(r[2] - 700, r[1], r[2], r[3]), all_screens=True)
        img.save(png)
        e = ctl.engine
        print(f"SELFTEST bars={info} title={ctl.title!r} playing={ctl.playing} frames={e.frames} "
              f"ring_max={float(abs(e.ring).max()):.3f} taskbar={r}")
        QApplication.quit()

    if not mgr.bars:
        CFG["show_on"] = "all"
        mgr.reposition()
    QTimer.singleShot(500, start)
    QTimer.singleShot(4500, shot)


def main():
    if sys.stderr is None:
        sys.stderr = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    import faulthandler
    faulthandler.enable(sys.stderr)
    import traceback
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")  # 曲名含 ⧸、emoji 時 cp950 會炸
        except Exception:
            pass
    sys.excepthook = lambda *ei: log_msg("[excepthook]\n" + "".join(traceback.format_exception(*ei)))
    if CFG.get("_load_error"):
        log_msg(CFG.pop("_load_error"))
    selftest = sys.argv[sys.argv.index("--selftest") + 1] if "--selftest" in sys.argv else None
    mutex = win32event.CreateMutex(None, False, "Local\\TaskbarPlayerSingleInstance")  # noqa: F841
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    mgr = Manager(app)
    if selftest:
        run_selftest(mgr, selftest)
    code = app.exec()
    mgr.ctl.engine.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
