import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import library as L  # noqa: E402


def touch(root, rel):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return str(p)


def make(tmp_path):
    for r in ["a.mp3", "b.txt", "S/10.mp3", "S/2.mp3", "S/1.mp3", "S/sub/3.flac",
              "N/x⧸y ｜ 🎵 [abcdefghijk].mp3", "N/deep/z.wav", "N/skip.m4a"]:
        touch(tmp_path, r)
    return tmp_path


def test_natural_sort():
    assert sorted(["10", "9", "01"], key=L.natural_key) == ["01", "9", "10"]


def test_suite_grouping_and_order(tmp_path):
    units = L.scan(str(make(tmp_path)), ["S"])
    suite = [u for u in units if u.is_suite]
    assert len(suite) == 1
    names = [os.path.basename(t) for t in suite[0].tracks]
    assert names == ["1.mp3", "2.mp3", "10.mp3", "3.flac"]  # 根層先自然排序，子資料夾排在 sub/ 之後


def test_loose_and_nested_singles(tmp_path):
    units = L.scan(str(make(tmp_path)), [])
    assert all(not u.is_suite and len(u.tracks) == 1 for u in units)
    assert len(units) == 1 + 4 + 2  # a.mp3 + S(4) + N(2)；txt、m4a 不算


def test_missing_root(tmp_path):
    assert L.scan(str(tmp_path / "nope")) is None


def test_title_strips_youtube_id_and_suite(tmp_path):
    units = L.scan(str(make(tmp_path)), ["S"])
    single = [u for u in units if "abcdefghijk" in u.key][0]
    assert L.track_title(single.tracks[0], single) == "x⧸y ｜ 🎵"
    s = [u for u in units if u.is_suite][0]
    assert L.track_title(s.tracks[0], s) == "S — 1"


def test_bag_no_immediate_repeat(tmp_path):
    units = L.scan(str(make(tmp_path)), [])
    for seed in range(30):
        pl = L.Playlist(units, random.Random(seed))
        seq = [pl.next()[0].key for _ in range(len(units) * 4)]
        assert all(a != b for a, b in zip(seq, seq[1:]))
        assert sorted(seq[:len(units)]) == sorted(u.key for u in units)  # 一輪每個恰好一次


def test_next_within_suite_then_unit(tmp_path):
    units = L.scan(str(make(tmp_path)), ["S"])
    pl = L.Playlist(units, random.Random(1))
    while True:
        u, i, _ = pl.next()
        if u.is_suite:
            break
    assert i == 0
    for n in range(1, len(u.tracks)):
        u2, i2, _ = pl.next()
        assert u2.key == u.key and i2 == n
    u3, _, _ = pl.next()
    assert u3.key != u.key


def test_prev_semantics(tmp_path):
    units = L.scan(str(make(tmp_path)), [])
    pl = L.Playlist(units, random.Random(2))
    a = pl.next()
    b = pl.next()
    assert pl.prev(10.0)[2] == b[2]      # >3s 重播
    assert pl.prev(1.0)[2] == a[2]       # 否則回上一首
    assert pl.prev(1.0)[2] == a[2]       # 無歷史則重播
    assert pl.next() is not None


def test_empty(tmp_path):
    pl = L.Playlist(L.scan(str(tmp_path), []))
    assert pl.next() is None and pl.current() is None
