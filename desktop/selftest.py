"""Offline packaged-runtime verification; does not start remote control."""
import io
import json
from pathlib import Path
import tempfile
import tkinter as tk
from PIL import Image
import native
from server import tls_context

def run(output):
    result = {}
    root = tk.Tk()
    root.withdraw()
    root.update()
    root.destroy()
    result['tk'] = True
    with Image.open(io.BytesIO(native.screen())) as im:
        result['screen'] = {'format': im.format, 'size': list(im.size)}
    result['clipboard_read'] = isinstance(native.clipboard_get(), str)
    position = native.cursor()
    result['cursor_read'] = 0 <= position['x'] <= 1 and 0 <= position['y'] <= 1
    with tempfile.TemporaryDirectory() as folder:
        _, fp = tls_context(Path(folder))
        result['tls_certificate'] = len(fp) == 24
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
