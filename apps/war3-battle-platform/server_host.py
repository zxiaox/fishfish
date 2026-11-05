"""Start a TLS-protected lobby broker on the operator's computer."""
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import socket
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
    def __init__(self,directory,port,callback,ipv6_enabled=False):
        self.cert,self.key,self.fingerprint=ensure_certificate(directory); self.port=port; self.callback=callback; self.ipv6_enabled=ipv6_enabled
        self.loop=None; self.broker=None; self.thread=None
    def start(self):
        self.thread=threading.Thread(target=self._run,daemon=True); self.thread.start()
    def _run(self):
        self.loop=asyncio.new_event_loop(); asyncio.set_event_loop(self.loop)
        async def run():
            try:
                ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(self.cert,self.key)
                self.broker=Broker(); server=await self.broker.start('0.0.0.0',self.port,ctx)
                servers=[server]; ipv6_active=False; ipv6_error=''
                if self.ipv6_enabled:
                    ipv6_socket=None
                    try:
                        ipv6_socket=socket.socket(socket.AF_INET6,socket.SOCK_STREAM)
                        ipv6_socket.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
                        ipv6_socket.setblocking(False)
                        ipv6_socket.bind(('::',server.sockets[0].getsockname()[1])); ipv6_socket.listen(socket.SOMAXCONN)
                        ipv6_server=await self.broker.start(None,None,ctx,sock=ipv6_socket)
                        servers.append(ipv6_server); ipv6_active=True
                    except OSError as exc:
                        if ipv6_socket: ipv6_socket.close()
                        ipv6_error=str(exc)
                self.callback('server_ready',{'fingerprint':self.fingerprint, 'ipv6_active':ipv6_active, 'ipv6_requested':self.ipv6_enabled, 'ipv6_error':ipv6_error, 'port':server.sockets[0].getsockname()[1]})
                await asyncio.gather(*(item.serve_forever() for item in servers))
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
