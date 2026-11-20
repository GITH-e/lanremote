"""Authenticated TLS LAN protocol; all file paths are server owned."""
import datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import ssl
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

MAX_FILE = 2 * 1024**3

def safe_name(value):
    value = ''.join('_' if ch in '<>:"/\\|?*' or ord(ch) < 32 else ch for ch in value)
    value = value.strip(' .')[:160] or 'file'
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}:
        value = '_' + value
    return value

def tls_context(folder):
    folder.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = folder/'cert.pem', folder/'key.pem'
    if not cert_path.exists() or not key_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'LanRemote')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-datetime.timedelta(days=1))
                .not_valid_after(now+datetime.timedelta(days=3650)).sign(key, hashes.SHA256()))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    fingerprint = cert.fingerprint(hashes.SHA256()).hex()[:24].upper()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert_path, key_path)
    return ctx, fingerprint

class State:
    def __init__(self, folder, native, approve=lambda ip: False, log=lambda msg: None):
        self.folder = Path(folder)
        self.inbox = self.folder/'收到的文件'
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.native, self.approve, self.log = native, approve, log
        self.pin = f'{secrets.randbelow(100000000):08d}'
        self.token = None
        self.expires = 0
        self.files = {}
        self.lock = threading.RLock()
        self.failures = []
        self.active = True
        self.pairing = False
        self.last_frame = (0, b'')
        self.frame_lock = threading.Lock()

    def authorized(self, token):
        with self.lock:
            return self.active and self.token and time.monotonic() < self.expires and hmac.compare_digest(token, self.token)

    def pair(self, pin, ip):
        with self.lock:
            now = time.monotonic()
            self.failures = [t for t in self.failures if now-t < 60]
            if len(self.failures) >= 5 or self.pairing:
                self.log('配对暂未受理：尝试过多或已有请求等待确认（'+ip+'）')
                return None
            self.failures.append(now)
            if not self.active or not hmac.compare_digest(str(pin), self.pin):
                self.log('配对码不匹配：'+ip+'；请填写当前电脑窗口中的配对码')
                return None
            self.pairing = True
        try:
            self.log('收到有效配对请求，等待电脑确认：'+ip)
            if not self.approve(ip):
                self.log('配对被拒绝或确认超时：'+ip)
                return None
            with self.lock:
                if not self.active:
                    return None
                self.token = secrets.token_urlsafe(32)
                self.expires = time.monotonic()+12*3600
                self.log('手机已连接：'+ip)
                return self.token
        finally:
            self.pairing = False

    def revoke(self):
        with self.lock:
            self.token = None
        self.native.release_mouse()

    def add_file(self, path):
        path = Path(path).resolve(strict=True)
        if not path.is_file():
            raise ValueError('Not a file')
        with self.lock:
            self.files[uuid.uuid4().hex] = path

    def frame(self):
        with self.frame_lock:
            now = time.monotonic()
            if now-self.last_frame[0] > .12:
                self.last_frame = (now, self.native.screen())
            return self.last_frame[1]

class Server(ThreadingHTTPServer):
    daemon_threads = True
    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(30)
        return sock, addr

def make_server(state, context, host='0.0.0.0', port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data, mime='application/json'):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def body(self, limit=512000):
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Chunked request unsupported')
            size = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= size <= limit:
                raise ValueError('Invalid body size')
            data = self.rfile.read(size)
            if len(data) != size:
                raise ValueError('Incomplete request')
            return json.loads(data)

        def do_GET(self):
            self.dispatch('GET')

        def do_POST(self):
            self.dispatch('POST')

        def dispatch(self, method):
            try:
                path = urlsplit(self.path)
                if path.path == '/hello' and method == 'GET':
                    self.reply(200, {'product':'LanRemote', 'version':'0.2.0', 'cursor':True})
                    return
                if path.path == '/pair' and method == 'POST':
                    token = state.pair(self.body(1024).get('pin', ''), self.client_address[0])
                    self.reply(200 if token else 403, {'token': token})
                    return
                token = self.headers.get('Authorization', '').removeprefix('Bearer ')
                if not state.authorized(token):
                    self.reply(401, {'error':'请在电脑端允许配对'})
                    return
                if path.path == '/disconnect' and method == 'POST':
                    state.revoke()
                    self.reply(200, {'ok':True})
                elif path.path == '/cursor' and method == 'GET':
                    self.reply(200, state.native.cursor())
                elif path.path == '/screen' and method == 'GET':
                    self.reply(200, state.frame(), 'image/jpeg')
                elif path.path == '/mouse' and method == 'POST':
                    state.native.mouse(self.body(1024))
                    self.reply(200, {'ok': True})
                elif path.path == '/clipboard':
                    if method == 'POST':
                        value = self.body().get('text')
                        if not isinstance(value, str) or len(value) > 100000:
                            raise ValueError('Text too long')
                        state.native.clipboard_set(value)
                    self.reply(200, {'text':state.native.clipboard_get()})
                elif path.path == '/files' and method == 'GET':
                    with state.lock:
                        listing = [{'id':key,'name':p.name,'size':p.stat().st_size} for key,p in state.files.items() if p.is_file()]
                    self.reply(200, listing)
                elif path.path == '/download' and method == 'GET':
                    key = parse_qs(path.query).get('id', [''])[0]
                    with state.lock:
                        target = state.files.get(key)
                    if not target:
                        self.reply(404, {'error':'文件不存在'})
                        return
                    with target.open('rb') as f:
                        size = os.fstat(f.fileno()).st_size
                        self.send_response(200)
                        self.send_header('Content-Length', str(size))
                        self.send_header('Content-Type','application/octet-stream')
                        self.end_headers()
                        remaining = size
                        while remaining:
                            if not state.authorized(token):
                                return
                            chunk = f.read(min(65536, remaining))
                            if not chunk:
                                return
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                elif path.path == '/upload' and method == 'POST':
                    if self.headers.get('Transfer-Encoding'):
                        raise ValueError('需要明确文件长度')
                    size = int(self.headers.get('Content-Length', '-1'))
                    if not 0 <= size <= MAX_FILE:
                        raise ValueError('单个文件最大 2 GB')
                    name = safe_name(parse_qs(path.query).get('name',['file'])[0])
                    unique = uuid.uuid4().hex[:12]
                    target = state.inbox / (unique+'_'+name)
                    partial = state.inbox / (unique+'.part')
                    try:
                        with partial.open('xb') as f:
                            remaining = size
                            while remaining:
                                if not state.authorized(token):
                                    raise ValueError('连接已撤销')
                                chunk = self.rfile.read(min(65536,remaining))
                                if not chunk:
                                    raise ValueError('文件传输中断')
                                f.write(chunk)
                                remaining -= len(chunk)
                        partial.replace(target)
                    finally:
                        partial.unlink(missing_ok=True)
                    state.log('收到文件：'+name)
                    self.reply(200, {'ok':True, 'name':target.name})
                else:
                    self.reply(404, {'error':'Not found'})
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as e:
                self.reply(400, {'error':str(e)})
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass
            except Exception as e:
                state.log('操作失败：'+str(e))
                try:
                    self.reply(500, {'error':'电脑端操作失败，请查看电脑端日志'})
                except OSError:
                    pass
    server = Server((host, port), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    return server
