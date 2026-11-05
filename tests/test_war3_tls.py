import asyncio
import importlib.util
import socket
import queue
import ssl
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path('apps/war3-battle-platform').resolve()))
from server_host import ensure_certificate, HostedBroker
from mesh import open_pinned, send_json, read_json
from server.broker import Broker

class TlsTests(unittest.IsolatedAsyncioTestCase):
    async def test_generated_identity_and_fingerprint_pinning(self):
        with tempfile.TemporaryDirectory() as directory:
            cert,key,fingerprint=ensure_certificate(directory)
            self.assertEqual(ensure_certificate(directory)[2],fingerprint)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,key)
            broker=Broker(); server=await broker.start('127.0.0.1',0,context); port=server.sockets[0].getsockname()[1]
            def good():
                with open_pinned('127.0.0.1',port,fingerprint) as connection:
                    send_json(connection,{'type':'hello'}); return read_json(connection)['type']
            try:
                self.assertEqual(await asyncio.to_thread(good),'welcome')
                with self.assertRaises(ValueError): await asyncio.to_thread(open_pinned,'127.0.0.1',port,'0'*64)
            finally: await broker.close()

    async def test_hosted_dual_stack_and_fingerprint(self):
        try:
            with socket.socket(socket.AF_INET6,socket.SOCK_STREAM) as probe: probe.bind(('::1',0))
        except OSError: self.skipTest('IPv6 loopback unavailable')
        events=queue.Queue()
        with tempfile.TemporaryDirectory() as directory:
            host=HostedBroker(directory,0,lambda kind,info:events.put((kind,info)),ipv6_enabled=True)
            host.start()
            try:
                kind,info=await asyncio.to_thread(events.get,True,5)
                self.assertEqual(kind,'server_ready'); self.assertTrue(info['ipv6_active'],info['ipv6_error'])
                def connect(address):
                    with open_pinned(address,info['port'],info['fingerprint']) as sock:
                        send_json(sock,{'type':'hello'}); return read_json(sock)['type']
                for address in ('127.0.0.1','::1'):
                    self.assertEqual(await asyncio.to_thread(connect,address),'welcome')
                with self.assertRaises(ValueError): await asyncio.to_thread(open_pinned,'::1',info['port'],'0'*64)
            finally: host.stop()

if __name__ == '__main__': unittest.main()
