"""Start a TLS-protected lobby broker on the operator's computer."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
from pathlib import Path
import ssl
import threading
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from server.broker import Broker


def ensure_certificate(directory):
    directory=Path(directory); directory.mkdir(parents=True, exist_ok=True)
    cert_path=directory/'server-cert.pem'; key_path=directory/'server-key.pem'
    if cert_path.exists() != key_path.exists(): raise ValueError('Incomplete existing server certificate')
    if not cert_path.exists():
        key=ec.generate_private_key(ec.SECP256R1())
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'FishFish War3 Lobby')])
        now=datetime.now(timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
              .not_valid_after(now+timedelta(days=3650)).sign(key,hashes.SHA256()))
        key_bytes=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        cert_bytes=cert.public_bytes(serialization.Encoding.PEM)
        with key_path.open('xb') as handle: handle.write(key_bytes)
        try:
            key_path.chmod(0o600)
            with cert_path.open('xb') as handle: handle.write(cert_bytes)
        except Exception:
            key_path.unlink(missing_ok=True); raise
    cert=x509.load_pem_x509_certificate(cert_path.read_bytes())
    fingerprint=hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return cert_path,key_path,fingerprint


class HostedBroker:
    def __init__(self,directory,port,callback):
        self.cert,self.key,self.fingerprint=ensure_certificate(directory); self.port=port; self.callback=callback
        self.loop=None; self.broker=None; self.thread=None
    def start(self):
        self.thread=threading.Thread(target=self._run,daemon=True); self.thread.start()
    def _run(self):
        self.loop=asyncio.new_event_loop(); asyncio.set_event_loop(self.loop)
        async def run():
            try:
                ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(self.cert,self.key)
                self.broker=Broker(); server=await self.broker.start('0.0.0.0',self.port,ctx)
                self.callback('server_ready',self.fingerprint)
                async with server: await server.serve_forever()
            except asyncio.CancelledError: pass
            except Exception as exc: self.callback('server_error',str(exc))
            finally:
                if self.broker: await self.broker.close()
        self.task=self.loop.create_task(run())
        try: self.loop.run_until_complete(self.task)
        finally: self.loop.close()
    def stop(self):
        if self.loop and self.loop.is_running(): self.loop.call_soon_threadsafe(self.task.cancel)
        if self.thread: self.thread.join(timeout=3)
