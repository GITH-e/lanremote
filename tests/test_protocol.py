import http.client
import json
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop'))
from server import State, make_server, safe_name, tls_context

class FakeNative:
    def __init__(self):
        self.text = ''
        self.moves = []
    def screen(self): return b'test-jpeg'
    def mouse(self, data): self.moves.append(data)
    def clipboard_get(self): return self.text
    def clipboard_set(self, value): self.text = value
    def release_mouse(self): pass
    def cursor(self): return {'x':.25,'y':.75,'visible':True}

class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.native = FakeNative()
        self.state = State(self.tmp.name, self.native, approve=lambda ip:True)
        context, self.fp = tls_context(Path(self.tmp.name))
        self.server = make_server(self.state, context, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.token = ''
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()
    def request(self, method, path, body=None, raw=False):
        conn = http.client.HTTPSConnection('127.0.0.1', self.server.server_port, context=ssl._create_unverified_context(), timeout=4)
        headers={'Authorization':'Bearer '+self.token}
        payload=body if raw else (json.dumps(body).encode() if body is not None else None)
        conn.request(method,path,payload,headers)
        response=conn.getresponse()
        status,data=response.status,response.read()
        conn.close()
        return status,data
    def pair(self):
        status,data=self.request('POST','/pair',{'pin':self.state.pin})
        self.assertEqual(status,200)
        self.token=json.loads(data)['token']
    def test_auth_and_revocation(self):
        self.assertEqual(self.request('GET','/screen')[0],401)
        self.assertEqual(self.request('POST','/mouse',{'action':'left'})[0],401)
        self.assertFalse(self.native.moves)
        self.assertEqual(self.request('POST','/pair',{'pin':'wrong'})[0],403)
        self.pair()
        self.assertEqual(self.request('GET','/screen'),(200,b'test-jpeg'))
        self.assertEqual(self.request('POST','/disconnect',{})[0],200)
        self.assertEqual(self.request('GET','/clipboard')[0],401)
    def test_reachability_does_not_require_or_grant_control(self):
        self.state.approve=lambda ip:self.fail('Reachability must not ask for approval')
        status,data=self.request('GET','/hello')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data),{'product':'LanRemote','version':'0.2.0','cursor':True})
        self.assertIsNone(self.state.token)
        self.assertEqual(self.request('GET','/screen')[0],401)
    def test_cursor_requires_pairing(self):
        self.assertEqual(self.request('GET','/cursor')[0],401)
        self.pair()
        status,data=self.request('GET','/cursor')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data),{'x':.25,'y':.75,'visible':True})
        self.state.revoke()
        self.assertEqual(self.request('GET','/cursor')[0],401)
    def test_clipboard_unicode_and_mouse(self):
        self.pair()
        value='文件与剪贴板 😀\n第二行'
        self.assertEqual(self.request('POST','/clipboard',{'text':value})[0],200)
        self.assertEqual(json.loads(self.request('GET','/clipboard')[1])['text'],value)
        self.assertEqual(self.request('POST','/mouse',{'action':'left','x':.2,'y':.4})[0],200)
        self.assertEqual(len(self.native.moves),1)
        self.assertEqual(self.request('POST','/clipboard',{'text':1})[0],400)
    def test_file_roundtrip_and_allowlist(self):
        self.pair()
        content=bytes(range(256))*2048
        self.assertEqual(self.request('POST','/upload?name=..%2F..%2FCON.txt',content,True)[0],200)
        received=list(self.state.inbox.iterdir())
        self.assertEqual(len(received),1)
        self.assertEqual(received[0].read_bytes(),content)
        self.assertEqual(received[0].parent,self.state.inbox)
        self.state.add_file(received[0])
        listing=json.loads(self.request('GET','/files')[1])
        self.assertEqual(self.request('GET','/download?id='+listing[0]['id']),(200,content))
        self.assertEqual(self.request('GET','/download?id=../../cert.pem')[0],404)
        self.assertFalse(list(self.state.inbox.glob('*.part')))
    def test_pair_rate_limit_and_confirmation(self):
        self.state.approve=lambda ip:False
        self.assertEqual(self.request('POST','/pair',{'pin':self.state.pin})[0],403)
        for _ in range(4):
            self.assertEqual(self.request('POST','/pair',{'pin':'bad'})[0],403)
        self.state.approve=lambda ip:True
        self.assertEqual(self.request('POST','/pair',{'pin':self.state.pin})[0],403)
    def test_names_and_certificate_persistence(self):
        self.assertEqual(safe_name('CON.txt'),'_CON.txt')
        self.assertNotIn('/',safe_name('../../evil'))
        _, other=tls_context(Path(self.tmp.name))
        self.assertEqual(self.fp,other)
        self.assertEqual(len(other),24)
    def test_limits_and_expiry(self):
        self.pair()
        conn=http.client.HTTPSConnection('127.0.0.1',self.server.server_port,context=ssl._create_unverified_context(),timeout=4)
        conn.request('POST','/upload?name=big.bin',b'',{'Authorization':'Bearer '+self.token,'Content-Length':str(2*1024**3+1)})
        response=conn.getresponse()
        self.assertEqual(response.status,400)
        response.read()
        conn.close()
        self.assertEqual(list(self.state.inbox.iterdir()),[])
        self.state.expires=0
        self.assertEqual(self.request('GET','/files')[0],401)

if __name__=='__main__':
    unittest.main()
