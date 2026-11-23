"""Validate embedded and bundled PNG assets using only the stdlib.

Catches corrupt base64/image data that would crash the frozen exe at
startup with _tkinter.TclError (e.g. 'invalid filter type 26').
Run: python3 -m unittest discover -s tests -v
"""
import base64
import json
import re
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PNG_SIG = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def validate_png(data: bytes, name="png") -> None:
    assert data[:8] == PNG_SIG, f"{name}: bad signature"
    pos = 8
    idat = b""
    w = h = ct = None
    seen_iend = False
    while pos < len(data):
        ln = int.from_bytes(data[pos:pos + 4], "big")
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        crc = int.from_bytes(data[pos + 8 + ln:pos + 12 + ln], "big")
        assert crc == (zlib.crc32(typ + chunk) & 0xFFFFFFFF), f"{name}: bad CRC in {typ}"
        if typ == b"IHDR":
            w, h, bd, ct, comp, filt, inter = struct.unpack(">IIBBBBB", chunk)
            assert comp == 0 and filt == 0 and inter == 0, f"{name}: unsupported IHDR"
            assert bd == 8, f"{name}: expected 8-bit depth"
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            seen_iend = True
            break
        pos += 12 + ln
    assert seen_iend and w and h, f"{name}: missing IEND/IHDR"
    raw = zlib.decompress(idat)
    stride = w * CHANNELS[ct] + 1
    assert len(raw) == stride * h, f"{name}: decompressed size mismatch"
    for i in range(h):
        f = raw[i * stride]
        assert 0 <= f <= 4, f"{name}: invalid filter type {f} on row {i}"


class TestPlaceholderPng(unittest.TestCase):
    def test_embedded_placeholder_is_valid_png(self):
        src = (ROOT / "brotato_save_editor.py").read_text(encoding="utf-8")
        m = re.search(r'PLACEHOLDER_PNG = "([A-Za-z0-9+/=]+)"', src)
        self.assertIsNotNone(m, "PLACEHOLDER_PNG literal not found")
        b64 = m.group(1)
        self.assertEqual(len(b64) % 4, 0, "base64 length must be a multiple of 4")
        data = base64.b64decode(b64, validate=True)
        validate_png(data, "PLACEHOLDER_PNG")


class TestIconFiles(unittest.TestCase):
    def test_manifest_entries_exist_and_are_valid_pngs(self):
        icons = ROOT / "assets" / "icons"
        manifest = json.loads((icons / "manifest.json").read_text(encoding="utf-8"))
        self.assertGreater(len(manifest), 500)
        for key, fname in manifest.items():
            p = icons / fname
            self.assertTrue(p.is_file(), f"{key}: missing {fname}")
            validate_png(p.read_bytes(), key)

    def test_all_pngs_in_icon_dir_are_valid(self):
        icons = ROOT / "assets" / "icons"
        files = list(icons.glob("*.png"))
        self.assertGreater(len(files), 500)
        for p in files:
            validate_png(p.read_bytes(), p.name)


if __name__ == "__main__":
    unittest.main()
