import os
from pathlib import Path
import queue
import socket
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import native
from server import State, tls_context, make_server


def main():
    root = tk.Tk()
    root.title('近控 LanRemote 0.2.0 · 电脑端')
    root.geometry('720x650')
    events = queue.Queue()
    folder = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'LanRemote'
    state = State(folder, native, log=lambda s: events.put(('log', s)))
    server = None
    pending = []
    def approve(ip):
        signal = threading.Event()
        result = [False]
        events.put(('approve', (ip, signal, result)))
        signal.wait(25)
        return result[0]
    state.approve = approve
    ctx, fingerprint = tls_context(folder)
    panel = ttk.Frame(root, padding=24)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='近控 · 手机连接你的电脑', font=('Microsoft YaHei UI', 20, 'bold')).pack(anchor='w')
    ttk.Label(panel, text='同一局域网即可使用 · 无账号 · 不经过外部服务器').pack(anchor='w', pady=(6,18))
    try:
        addresses = sorted({v[4][0] for v in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET) if not v[4][0].startswith('127.')})
    except OSError:
        addresses = []
    def field(label, value):
        ttk.Label(panel, text=label).pack(anchor='w')
        entry = ttk.Entry(panel, font=('Consolas', 13))
        entry.insert(0, value)
        entry.configure(state='readonly')
        entry.pack(fill='x', pady=(3,10))
    field('手机填写电脑地址（选与手机同一网段的 IPv4 地址）', ' / '.join(a+':8765' for a in addresses) or '请运行 ipconfig 查看 IPv4 地址，端口 8765')
    field('配对码（本次启动有效）', state.pin)
    field('证书校验码（24 位，可忽略空格和大小写）', ' '.join(fingerprint[i:i+4] for i in range(0,24,4)))
    status = tk.StringVar(value='尚未启动')
    ttk.Label(panel, textvariable=status, foreground='#16784b').pack(anchor='w', pady=4)
    def revoke():
        state.revoke()
        status.set('已断开手机；重新连接需要电脑确认')
    def share():
        for path in filedialog.askopenfilenames(title='选择允许手机下载的文件'):
            state.add_file(path)
            events.put(('log', '已分享：'+Path(path).name))
    buttons = ttk.Frame(panel)
    buttons.pack(fill='x', pady=10)
    ttk.Button(buttons, text='选择文件发给手机', command=share).pack(side='left')
    ttk.Button(buttons, text='打开收到的文件', command=lambda:os.startfile(state.inbox)).pack(side='left', padx=8)
    ttk.Button(buttons, text='断开手机', command=revoke).pack(side='left')
    ttk.Button(panel, text='清空电脑分享列表', command=lambda:clear_files()).pack(anchor='w')
    def clear_files():
        with state.lock:
            state.files.clear()
        events.put(('log','已清空分享列表（原文件保留）'))
    ttk.Label(panel, text='手机默认触摸板模式：滑动移光标、轻点点击、长按拖拽。关闭此窗口即停止服务。', wraplength=650).pack(anchor='w', pady=10)
    log = tk.Text(panel, height=8, state='disabled', wrap='word')
    log.pack(fill='both', expand=True)
    def append(text):
        log.configure(state='normal')
        log.insert('end', text+'\n')
        log.see('end')
        log.configure(state='disabled')
    def pump():
        while not events.empty():
            kind, payload = events.get_nowait()
            if kind == 'log':
                append(payload)
            else:
                ip, signal, result = payload
                root.deiconify()
                dialog = tk.Toplevel(root)
                dialog.transient(root)
                dialog.title('允许手机控制？')
                pending.append((dialog, signal, result))
                ttk.Label(dialog, text=f'来自 {ip} 的手机请求控制电脑。\n请确认这是你自己的手机。', padding=20).pack()
                def answer(ok, d=dialog, s=signal, r=result):
                    if not s.is_set():
                        r[0] = ok
                        s.set()
                    if d.winfo_exists():
                        d.destroy()
                ttk.Button(dialog, text='允许连接', command=lambda a=answer:a(True)).pack(side='left', padx=20, pady=12)
                ttk.Button(dialog, text='拒绝', command=lambda a=answer:a(False)).pack(side='right', padx=20, pady=12)
                dialog.protocol('WM_DELETE_WINDOW', lambda a=answer:a(False))
                dialog.after(24000, lambda a=answer:a(False))
                dialog.attributes('-topmost', True)
                dialog.after(1800, lambda d=dialog: d.attributes('-topmost', False) if d.winfo_exists() else None)
                dialog.lift()
        root.after(100, pump)
    def close():
        state.active = False
        state.revoke()
        for _, signal, result in pending:
            result[0] = False
            signal.set()
        if server:
            threading.Thread(target=server.shutdown, daemon=True).start()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    try:
        server = make_server(state, ctx)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        status.set('正在等待手机配对 · TCP 8765')
        append('手机连接后，此处会记录配对请求。没有记录通常表示地址错误、网络隔离或防火墙拦截。')
        append('Windows 网络若为“公用”，仅允许专用网络的规则不会生效；请按说明配置本地子网 TCP 8765。')
    except OSError as e:
        messagebox.showerror('无法启动', str(e))
        root.destroy()
        return
    pump()
    root.mainloop()

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from selftest import run
        run(Path(sys.argv[2]))
    else:
        main()
