"""Real Win32 smoke test. Does not move mouse or alter clipboard contents."""
import io
import json
from pathlib import Path
import sys
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
import native
from PIL import Image

root=tk.Tk()
root.withdraw()
root.update()
result={'tk':True}
root.destroy()
frame=native.screen()
with Image.open(io.BytesIO(frame)) as im:
    result['capture_format']=im.format
    result['capture_size']=list(im.size)
    assert im.format=='JPEG' and 0<im.width<=1280
assert isinstance(native.clipboard_get(),str)
result['clipboard_read']=True
for bad in ({'action':'left','x':-1,'y':0},{'action':'unknown'}):
    try:
        native.mouse(bad)
        raise AssertionError('Invalid mouse command accepted')
    except ValueError:
        pass
result['invalid_mouse_rejected']=True
print(json.dumps(result))
