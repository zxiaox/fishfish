import asyncio
import importlib.util
import socket
import ssl
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path('apps/war3-battle-platform').resolve()))
from server_host import ensure_certificate
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

if __name__ == '__main__': unittest.main()
