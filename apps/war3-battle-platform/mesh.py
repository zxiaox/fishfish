"""Client for a self-hosted War3 lobby directory and TCP relay."""
import base64
import hashlib
import json
import queue
import select
import socket
import ssl
import struct
import threading
import time
import uuid
from network import LAN_PORT, search_packet, parse_announcement, rewrite_port, cancel_packet, _local_addresses


def send_json(sock, value, lock=None):
    data = json.dumps(value, separators=(',', ':')).encode() + b'\n'
    if lock:
        with lock: sock.sendall(data)
    else: sock.sendall(data)


def read_json(sock, data=None):
    # Preserve partial frames across timeouts and never consume game bytes.
    if data is None: data = bytearray()
    while len(data) < 8192:
        part = sock.recv(1)
        if not part: raise ConnectionError('Connection closed')
        if part == b'\n':
            result = json.loads(data)
            data.clear()
            if not isinstance(result, dict): raise ValueError('Invalid server message')
            return result
        data.extend(part)
    raise ValueError('Server message too large')


def open_pinned(address, port, fingerprint, timeout=8):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False; context.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection((address, port), timeout=timeout)
    try:
        sock = context.wrap_socket(raw, server_hostname=address)
        actual = hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
        if actual != fingerprint.lower().replace(':', ''):
            sock.close(); raise ValueError('Server certificate fingerprint does not match')
        return sock
    except Exception:
        raw.close(); raise


def relay_pair(a, b, stop_event):
    """Move TCP game bytes both ways until either side closes."""
    try:
        a.setblocking(False); b.setblocking(False)
        while not stop_event.is_set():
            readable, _, _ = select.select([a, b], [], [], .5)
            for candidate in (a, b):
                if isinstance(candidate, ssl.SSLSocket) and candidate.pending() and candidate not in readable:
                    readable.append(candidate)
            for source in readable:
                try: data = source.recv(65536)
                except (ssl.SSLWantReadError, BlockingIOError): continue
                if not data: return
                dest = b if source is a else a
                dest.settimeout(8); dest.sendall(data); dest.setblocking(False)
    except (OSError, ValueError, ssl.SSLError): pass
    finally:
        for sock in (a,b):
            try: sock.close()
            except OSError: pass


class LobbyClient:
    def __init__(self, host, port, fingerprint, callback, *, connection_factory=None, game_udp_port=LAN_PORT, broadcast_host='255.255.255.255', broadcast_port=LAN_PORT):
        self.host=host; self.port=port; self.fingerprint=fingerprint; self.callback=callback
        self.connect_socket = connection_factory or (lambda: open_pinned(host, port, fingerprint))
        self.game_udp_port=game_udp_port; self.broadcast_host=broadcast_host; self.broadcast_port=broadcast_port
        self.stop_event=threading.Event(); self.send_lock=threading.Lock(); self.lock=threading.Lock()
        self.control=None; self.udp=None; self.lobbies={}; self.pending={}; self.active=set(); self.threads=[]; self.local_port=None; self.last_local=0
        self.local_addresses=_local_addresses()

    def start(self):
        self.control=self.connect_socket(); self.control.settimeout(8)
        send_json(self.control, {'type':'hello'})
        if read_json(self.control).get('type') != 'welcome': raise ValueError('Server rejected connection')
        self.control.settimeout(1)
        self.udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); self.udp.bind(('0.0.0.0',0)); self.udp.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1); self.udp.settimeout(.3)
        self.local_addresses.add('127.0.0.1')
        for fn in (self._control_loop, self._local_loop):
            thread=threading.Thread(target=fn,daemon=True); self.threads.append(thread); thread.start()
        self.callback('ready', '')

    def _send(self, data): send_json(self.control, data, self.send_lock)

    def _control_loop(self):
        last_ping=time.monotonic(); buffer=bytearray()
        try:
            while not self.stop_event.is_set():
                try: msg=read_json(self.control, buffer)
                except socket.timeout:
                    if time.monotonic()-last_ping>12: self._send({'type':'ping'}); last_ping=time.monotonic()
                    continue
                kind=msg.get('type')
                if kind=='lobbies': self._set_lobbies(msg.get('lobbies', []))
                elif kind=='incoming': self._spawn(self._host_relay,msg)
                elif kind=='outgoing': self._spawn(self._join_relay,msg)
                elif kind=='unavailable':
                    with self.lock: pending=self.pending.pop(msg.get('request'),None)
                    if pending: pending.close()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if not self.stop_event.is_set(): self.callback('error',str(exc))

    def _spawn(self, fn, *args):
        thread=threading.Thread(target=fn,args=args,daemon=True); self.threads.append(thread); thread.start()

    def _local_loop(self):
        last_query=0; last_published=None; last_announce=0
        try:
            while not self.stop_event.is_set():
                now=time.monotonic()
                if now-last_query>=3:
                    for game in ('TFT','ROC'):
                        for version in range(21,30): self.udp.sendto(search_packet(game,version),('127.0.0.1',self.game_udp_port))
                    last_query=now
                try: data, addr=self.udp.recvfrom(1401)
                except (socket.timeout, ConnectionResetError): data=None
                if data and addr[0]=='127.0.0.1' and addr[1]==self.game_udp_port and len(data)>=12:
                    version=struct.unpack_from('<I',data,8)[0]; edition='TFT' if data[4:8]==b'PX3W' else 'ROC'
                    try: game_id, game_port, name=parse_announcement(data,edition,version)
                    except ValueError: continue
                    with self.lock: self.local_port=game_port
                    self.last_local=time.monotonic()
                    encoded=base64.b64encode(data).decode('ascii')
                    if encoded != last_published:
                        self._send({'type':'publish','packet':encoded}); last_published=encoded
                if last_published and time.monotonic()-self.last_local>10:
                    self._send({'type':'withdraw'}); last_published=None
                    with self.lock: self.local_port=None
                # LAN clients forget lobbies without periodic announcements.
                if now-last_announce>=2:
                    self._announce_all(); last_announce=now
        except (OSError, ValueError) as exc:
            if not self.stop_event.is_set(): self.callback('error',str(exc))

    def _set_lobbies(self, records):
        if not isinstance(records,list) or len(records)>128: raise ValueError('Invalid lobby list')
        wanted={}
        for row in records:
            try:
                host=row['host']
                if not isinstance(host,str) or len(host)!=32: continue
                data=base64.b64decode(row['packet'],validate=True)
                edition='TFT' if data[4:8]==b'PX3W' else 'ROC'; version=struct.unpack_from('<I',data,8)[0]
                game_id, _, _ = parse_announcement(data,edition,version)
                wanted[host]=(data,game_id)
            except (KeyError, ValueError, TypeError, struct.error): continue
        with self.lock:
            for host in set(self.lobbies)-set(wanted):
                item=self.lobbies.pop(host)
                try: self.udp.sendto(cancel_packet(item['id']),(self.broadcast_host,self.broadcast_port))
                except OSError: pass
                item['listener'].close()
            for host,(packet,game_id) in wanted.items():
                if host in self.lobbies:
                    current=self.lobbies[host]
                    if current['id'] != game_id:
                        try: self.udp.sendto(cancel_packet(current['id']),(self.broadcast_host,self.broadcast_port))
                        except OSError: pass
                    current['packet']=packet; current['id']=game_id; continue
                listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM); listener.bind(('0.0.0.0',0)); listener.listen(8); listener.settimeout(.5)
                self.lobbies[host]={'listener':listener,'packet':packet,'id':game_id}
                self._spawn(self._accept,host,listener)
        self.callback('lobbies',str(len(wanted)))

    def _announce_all(self):
        with self.lock: entries=[(x['packet'],x['listener'].getsockname()[1]) for x in self.lobbies.values()]
        for packet,port in entries:
            self.udp.sendto(rewrite_port(packet,port),(self.broadcast_host,self.broadcast_port))

    def _accept(self, host, listener):
        while not self.stop_event.is_set():
            try: client,addr=listener.accept()
            except socket.timeout: continue
            except OSError: break
            if addr[0] not in self.local_addresses: client.close(); continue
            request=uuid.uuid4().hex
            with self.lock: self.pending[request]=client
            try: self._send({'type':'connect','host':host,'request':request})
            except OSError:
                with self.lock: self.pending.pop(request,None)
                client.close(); break

    def _attach(self, msg, side):
        sock=self.connect_socket(); sock.settimeout(15)
        send_json(sock,{'type':'attach','ticket':msg['ticket'],'secret':msg['secret'],'side':side})
        if read_json(sock).get('type')!='ready': sock.close(); raise ConnectionError('Relay rejected')
        return sock

    def _join_relay(self,msg):
        with self.lock: client=self.pending.pop(msg.get('request'),None)
        if not client: return
        try:
            remote=self._attach(msg,'join')
            with self.lock: self.active.update((client,remote))
            self.callback('game_connected',''); relay_pair(client,remote,self.stop_event)
        except (OSError, ValueError, KeyError) as exc:
            client.close(); self.callback('relay_error',str(exc))
        finally:
            with self.lock: self.active.discard(client)

    def _host_relay(self,msg):
        with self.lock: port=self.local_port
        if not port: return
        try:
            local=socket.create_connection(('127.0.0.1',port),timeout=5)
            try: remote=self._attach(msg,'host')
            except Exception: local.close(); raise
            with self.lock: self.active.update((local,remote))
            self.callback('game_connected',''); relay_pair(local,remote,self.stop_event)
        except (OSError, ValueError, KeyError) as exc: self.callback('relay_error',str(exc))

    def stop(self):
        self.stop_event.set()
        with self.lock:
            lobbies=list(self.lobbies.values()); self.lobbies.clear(); sockets=list(self.pending.values())+list(self.active); self.pending.clear(); self.active.clear()
        for item in lobbies:
            try: self.udp.sendto(cancel_packet(item['id']),(self.broadcast_host,self.broadcast_port))
            except OSError: pass
            sockets.append(item['listener'])
        for sock in sockets+[self.control,self.udp]:
            if sock:
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                try: sock.close()
                except OSError: pass
