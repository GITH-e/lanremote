"""Windows desktop operations. No service, elevation or persistence."""
import ctypes as c
from ctypes import wintypes as w
import io
import threading
from PIL import ImageGrab

u = c.WinDLL('user32', use_last_error=True)
k = c.WinDLL('kernel32', use_last_error=True)
u.SetProcessDPIAware()
u.GetClipboardData.restype = w.HANDLE
u.SetClipboardData.argtypes = [w.UINT, w.HANDLE]
u.SetClipboardData.restype = w.HANDLE
k.GlobalAlloc.argtypes = [w.UINT, c.c_size_t]
k.GlobalAlloc.restype = w.HGLOBAL
k.GlobalLock.argtypes = [w.HGLOBAL]
k.GlobalLock.restype = c.c_void_p
k.GlobalUnlock.argtypes = [w.HGLOBAL]
k.GlobalFree.argtypes = [w.HGLOBAL]
clip_lock = threading.Lock()
mouse_lock = threading.RLock()
release_timer = None
held = False

def cursor():
    point = w.POINT()
    if not u.GetCursorPos(c.byref(point)):
        raise RuntimeError('无法读取鼠标位置')
    width, height = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    return {'x':max(0, min(1, point.x / max(1, width-1))),
            'y':max(0, min(1, point.y / max(1, height-1))),
            'visible':0 <= point.x < width and 0 <= point.y < height}

def screen():
    # Primary monitor only; coordinates match SetCursorPos on the primary monitor.
    im = ImageGrab.grab(all_screens=False)
    im.thumbnail((1280, 1280))
    out = io.BytesIO()
    im.convert('RGB').save(out, 'JPEG', quality=65)
    return out.getvalue()

def mouse(data):
    global release_timer, held
    with mouse_lock:
        _mouse(data)
        action = data['action']
        if action == 'down':
            held = True
        elif action in ('up', 'left'):
            held = False
        if release_timer:
            release_timer.cancel()
        if held:
            release_timer = threading.Timer(3, release_mouse)
            release_timer.daemon = True
            release_timer.start()

def _mouse(data):
    action = data['action']
    if action == 'scroll':
        delta = max(-5, min(5, int(data.get('delta', 0))))
        u.mouse_event(0x0800, 0, 0, delta * 120, 0)
        return
    if action not in ('move', 'left', 'right', 'down', 'up'):
        raise ValueError('Unknown mouse action')
    x, y = float(data['x']), float(data['y'])
    if not 0 <= x <= 1 or not 0 <= y <= 1:
        raise ValueError('Invalid coordinates')
    u.SetCursorPos(round(x * (u.GetSystemMetrics(0)-1)), round(y * (u.GetSystemMetrics(1)-1)))
    flags = {'move': (), 'left': (2, 4), 'right': (8, 16), 'down': (2,), 'up': (4,)}
    for flag in flags[action]:
        u.mouse_event(flag, 0, 0, 0, 0)

def release_mouse():
    global held
    with mouse_lock:
        held = False
        u.mouse_event(4, 0, 0, 0, 0)

def clipboard_get():
    with clip_lock:
        if not u.OpenClipboard(None):
            raise RuntimeError('剪贴板正忙，请重试')
        try:
            handle = u.GetClipboardData(13)
            if not handle:
                return ''
            ptr = k.GlobalLock(handle)
            if not ptr:
                raise RuntimeError('读取剪贴板失败')
            try:
                return c.wstring_at(ptr)[:100000]
            finally:
                k.GlobalUnlock(handle)
        finally:
            u.CloseClipboard()

def clipboard_set(text):
    raw = (text + '\0').encode('utf-16-le')
    with clip_lock:
        if not u.OpenClipboard(None):
            raise RuntimeError('剪贴板正忙，请重试')
        handle = None
        try:
            handle = k.GlobalAlloc(0x0042, len(raw))
            ptr = k.GlobalLock(handle)
            if not ptr:
                raise RuntimeError('分配剪贴板内存失败')
            c.memmove(ptr, raw, len(raw))
            k.GlobalUnlock(handle)
            u.EmptyClipboard()
            if not u.SetClipboardData(13, handle):
                raise RuntimeError('设置剪贴板失败')
            handle = None
        finally:
            if handle:
                k.GlobalFree(handle)
            u.CloseClipboard()
