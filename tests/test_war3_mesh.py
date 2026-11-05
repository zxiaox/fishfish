import asyncio
import importlib.util
import queue
import socket
import ssl
import tempfile
import struct
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path('apps/war3-battle-platform').resolve()))
from mesh import LobbyClient, open_pinned
from server_host import ensure_certificate
spec = importlib.util.spec_from_file_location('war3_broker_mesh', Path('apps/war3-battle-platform/server/broker.py'))
broker_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(broker_module)


def packet(port):
    data = bytearray(b'\xf7\x30\0\0PX3W'+struct.pack('<III',26,42,0)+b'Lobby\0'+bytes(21)+struct.pack('<H',port))
    struct.pack_into('<H',data,2,len(data)); return bytes(data)


class MeshTests(unittest.IsolatedAsyncioTestCase):
    async def test_detects_classic_127_from_local_adapter(self):
        events=[]; sent=[]; datagrams=[]
        client=LobbyClient('127.0.0.1',1,'',lambda kind,info: events.append((kind,info)),game_udp_port=6112)
        client.local_addresses={'192.0.2.10'}
        value=bytearray(packet(6113)); struct.pack_into('<I',value,8,27)
        class FakeSocket:
            def sendto(self, data, target): datagrams.append((data,target))
            def recvfrom(self, size): return bytes(value), ('192.0.2.10',6114)
        client.udp=FakeSocket()
        def publish(message):
            sent.append(message); client.stop_event.set()
        client._send=publish
        client._local_loop()
        self.assertIn(('local_found','Lobby'),events)
        self.assertEqual(sent[0]['type'],'publish')
        self.assertTrue(any(target==('192.0.2.10',6112) and data[8:12]==struct.pack('<I',27) for data,target in datagrams))
        self.assertEqual(client.local_game_address,'192.0.2.10')
        self.assertEqual(client.snapshot()['accepted'],1)
        self.assertEqual(client.snapshot()['last_source_port'],6114)

    async def test_automatic_discovery_and_relay(self):
        temporary=tempfile.TemporaryDirectory()
        cert,key,fingerprint=ensure_certificate(temporary.name)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,key)
        broker=broker_module.Broker(); server=await broker.start('127.0.0.1',0,context); broker_port=server.sockets[0].getsockname()[1]
        host_udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); host_udp.bind(('127.0.0.1',0)); host_udp.settimeout(.2)
        game_tcp=socket.socket(socket.AF_INET,socket.SOCK_STREAM); game_tcp.bind(('127.0.0.1',0)); game_tcp.listen(); game_tcp.settimeout(5)
        viewer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); viewer.bind(('127.0.0.1',0)); viewer.settimeout(8)
        stop=threading.Event(); failures=queue.Queue()
        def game_host():
            try:
                while not stop.is_set():
                    try: data,addr=host_udp.recvfrom(1024)
                    except socket.timeout: continue
                    if data[4:8]==b'PX3W' and data[8:12]==struct.pack('<I',26): host_udp.sendto(packet(game_tcp.getsockname()[1]),addr)
            except OSError: pass
        def game_stream():
            try:
                conn,_=game_tcp.accept()
                with conn:
                    assert conn.recv(1024)==b'war3-request'; conn.sendall(b'war3-reply')
            except Exception as exc: failures.put(exc)
        threading.Thread(target=game_host,daemon=True).start(); threading.Thread(target=game_stream,daemon=True).start()
        factory=lambda: open_pinned('127.0.0.1',broker_port,fingerprint)
        first=LobbyClient('127.0.0.1',broker_port,'',lambda *args:None,connection_factory=factory,game_udp_port=host_udp.getsockname()[1],broadcast_host='127.0.0.1',broadcast_port=viewer.getsockname()[1])
        second=LobbyClient('127.0.0.1',broker_port,'',lambda *args:None,connection_factory=factory,game_udp_port=1,broadcast_host='127.0.0.1',broadcast_port=viewer.getsockname()[1])
        try:
            await asyncio.to_thread(first.start); await asyncio.to_thread(second.start)
            data,_=await asyncio.to_thread(viewer.recvfrom,2048)
            self.assertEqual(data[1],0x30); port=struct.unpack_from('<H',data,len(data)-2)[0]
            def play():
                with socket.create_connection(('127.0.0.1',port),timeout=5) as client:
                    client.sendall(b'war3-request'); return client.recv(1024)
            self.assertEqual(await asyncio.to_thread(play),b'war3-reply')
            if not failures.empty(): raise failures.get()
        finally:
            first.stop(); second.stop(); stop.set(); host_udp.close(); game_tcp.close(); viewer.close(); await broker.close(); temporary.cleanup()
