"""曲庫邏輯（純 Python，不依賴 Qt）：掃描資料夾、組曲、洗牌袋、上一首／下一首。"""
import os
import random
import re
from dataclasses import dataclass, field

AUDIO_EXT = {".mp3", ".flac", ".wav", ".ogg"}  # miniaudio 能解的格式
_YT_ID = re.compile(r"\s*\[[A-Za-z0-9_-]{11}\]\s*$")
PREV_RESTART_S = 3.0


def natural_key(s):
    """自然排序：'2' 在 '10' 之前。"""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", s) if t != ""]


def _audio_files(folder):
    out = []
    for dp, dns, fns in os.walk(folder):
        dns.sort(key=natural_key)
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in AUDIO_EXT:
                out.append(os.path.join(dp, fn))
    out.sort(key=lambda p: [natural_key(x) for x in os.path.relpath(p, folder).split(os.sep)])
    return out


@dataclass
class Unit:
    key: str                 # 資料夾或檔案的完整路徑
    tracks: list = field(default_factory=list)
    is_suite: bool = False
    folder: str = ""         # 顯示用資料夾名


def scan(root, suites=()):
    """回傳播放單元 list；根目錄不存在回傳 None。"""
    if not root or not os.path.isdir(root):
        return None
    suites = set(suites)
    units = []
    try:
        entries = sorted(os.listdir(root), key=natural_key)
    except OSError:
        return None
    for name in entries:
        p = os.path.join(root, name)
        if os.path.isdir(p):
            files = _audio_files(p)
            if name in suites:
                if files:
                    units.append(Unit(p, files, True, name))
            else:
                units += [Unit(f, [f], False, name) for f in files]
        elif os.path.splitext(name)[1].lower() in AUDIO_EXT:
            units.append(Unit(p, [p], False, os.path.basename(root)))
    return units


def track_title(path, unit=None):
    stem = _YT_ID.sub("", os.path.splitext(os.path.basename(path))[0])
    if unit is not None and unit.is_suite:
        return f"{unit.folder} — {stem}"
    return stem


class Playlist:
    def __init__(self, units=None, rng=None):
        self.rng = rng or random.Random()
        self.units = {}
        self.bag = []
        self.history = []      # [(unit_key, idx)] 已播過的曲目（不含目前）
        self.cur = None        # (unit_key, idx)
        self.last_key = None
        self.set_units(units or [])

    def set_units(self, units):
        self.units = {u.key: u for u in units}
        self.bag = [k for k in self.bag if k in self.units]
        self.history = [h for h in self.history if h[0] in self.units]
        if self.cur and (self.cur[0] not in self.units or self.cur[1] >= len(self.units[self.cur[0]].tracks)):
            self.cur = None

    def reshuffle(self):
        self.bag = []

    def _draw(self):
        if not self.units:
            return None
        if not self.bag:
            self.bag = list(self.units)
            self.rng.shuffle(self.bag)
            if len(self.bag) > 1 and self.bag[0] == self.last_key:  # 洗牌交界不連播同一單元
                self.bag[0], self.bag[-1] = self.bag[-1], self.bag[0]
        k = self.bag.pop(0)
        self.last_key = k
        return k

    def current(self):
        """回傳 (unit, idx, path) 或 None。"""
        if not self.cur:
            return None
        u = self.units[self.cur[0]]
        return u, self.cur[1], u.tracks[self.cur[1]]

    def next(self):
        if self.cur:
            u = self.units[self.cur[0]]
            if u.is_suite and self.cur[1] + 1 < len(u.tracks):
                self.history.append(self.cur)
                self.cur = (u.key, self.cur[1] + 1)
                return self.current()
        k = self._draw()
        if k is None:
            self.cur = None
            return None
        if self.cur:
            self.history.append(self.cur)
        self.cur = (k, 0)
        return self.current()

    def prev(self, pos_s=0.0):
        """播放超過 3 秒＝重播本曲；否則回到上一首（無歷史則重播）。"""
        if self.cur is None:
            return self.next()
        if pos_s > PREV_RESTART_S or not self.history:
            return self.current()
        self.cur = self.history.pop()
        self.last_key = self.cur[0]
        return self.current()
