"""Classic Warcraft III LAN discovery bridge over an existing IP network.

Packet layout informed by WC3LanGame (MIT), https://github.com/Qyperion/WC3LanGame.
The program does not provide a VPN, NAT traversal, or transport encryption.
"""
import ipaddress
import select
import socket
import struct
import threading
import time

LAN_PORT = 6112
MAX_PACKET = 1400


def search_packet(game, version):
    if game not in ('TFT', 'ROC') or not 1 <= version <= 255:
        raise ValueError('Invalid game edition or version')
    return b'\xf7\x2f\x10\x00' + (b'PX3W' if game == 'TFT' else b'3RAW') + struct.pack('<II', version, 0)


def parse_announcement(data, game, version):
    if len(data) < 44 or len(data) > MAX_PACKET or data[:2] != b'\xf7\x30':
        raise ValueError('Invalid game announcement')
    if struct.unpack_from('<H', data, 2)[0] != len(data):
        raise ValueError('Invalid packet length')
    if data[4:8] != (b'PX3W' if game == 'TFT' else b'3RAW') or struct.unpack_from('<I', data, 8)[0] != version:
        raise ValueError('Unexpected game version')
    if b'\0' not in data[20:-22]:
        raise ValueError('Missing game name')
    port = struct.unpack_from('<H', data, len(data)-2)[0]
    if not port: raise ValueError('Invalid game port')
    game_id = struct.unpack_from('<I', data, 12)[0]
    name = data[20:data.index(b'\0', 20)].decode('utf-8', errors='replace')[:128]
    return game_id, port, name


def rewrite_port(data, port):
    if not 1 <= port <= 65535 or len(data) < 2: raise ValueError('Invalid proxy port')
    return data[:-2] + struct.pack('<H', port)


def cancel_packet(game_id):
    return b'\xf7\x33\x08\x00' + struct.pack('<I', game_id)


def _local_addresses():
    addresses = {'127.0.0.1'}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            addresses.add(info[4][0])
    except OSError:
        pass
    return addresses


class Bridge:
    def __init__(self, host, game, version, callback, *, discovery_port=LAN_PORT, broadcast_port=LAN_PORT, broadcast_host='255.255.255.255'):
        self.host = str(ipaddress.IPv4Address(host))
        self.game = game; self.version = version; self.callback = callback
        self.search = search_packet(game, version)
        self.discovery_port = discovery_port; self.broadcast_port = broadcast_port; self.broadcast_host = broadcast_host
        self.stop_event = threading.Event(); self.lock = threading.Lock(); self.threads = []
        self.active = set(); self.last_game = None; self.remote_port = None
        self.udp = None; self.listener = None

    def start(self):
        if self.listener is not None: raise RuntimeError('Already running')
        try:
            self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listener.bind(('0.0.0.0', 0)); self.listener.listen(8); self.listener.settimeout(.5)
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.bind(('0.0.0.0', 0)); self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1); self.udp.settimeout(.3)
            self.proxy_port = self.listener.getsockname()[1]
            self.local_addresses = _local_addresses()
            # Determine the local address Windows uses when routing to the host.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect((self.host, self.discovery_port)); self.local_addresses.add(probe.getsockname()[0])
            for target in (self._browse, self._accept):
                thread = threading.Thread(target=target, daemon=True); self.threads.append(thread); thread.start()
        except Exception:
            self.stop(); raise

    def _browse(self):
        last_query = 0; last_seen = 0
        while not self.stop_event.is_set():
            try:
                now = time.monotonic()
                if now - last_query >= 1:
                    self.udp.sendto(self.search, (self.host, self.discovery_port)); last_query = now
                try: packet, address = self.udp.recvfrom(MAX_PACKET + 1)
                except socket.timeout: packet = None
                if packet is not None and address[0] == self.host and address[1] == self.discovery_port:
                    try: game_id, port, name = parse_announcement(packet, self.game, self.version)
                    except ValueError: continue
                    with self.lock:
                        if self.last_game is not None and self.last_game != game_id: continue
                        self.remote_port = port; self.last_game = game_id
                    self.udp.sendto(rewrite_port(packet, self.proxy_port), (self.broadcast_host, self.broadcast_port))
                    if not last_seen: self.callback('found', name)
                    last_seen = time.monotonic()
                if last_seen and time.monotonic() - last_seen > 4:
                    with self.lock: game_id = self.last_game; self.remote_port = None; self.last_game = None
                    if game_id is not None: self.udp.sendto(cancel_packet(game_id), (self.broadcast_host, self.broadcast_port))
                    last_seen = 0; self.callback('lost', '')
            except OSError as exc:
                if not self.stop_event.is_set(): self.callback('error', str(exc))
                break

    def _accept(self):
        while not self.stop_event.is_set():
            try: client, address = self.listener.accept()
            except socket.timeout: continue
            except OSError: break
            with self.lock: port = self.remote_port
            if address[0] not in self.local_addresses or port is None:
                client.close(); continue
            thread = threading.Thread(target=self._relay, args=(client, port), daemon=True)
            self.threads.append(thread); thread.start()

    def _relay(self, client, port):
        remote = None
        try:
            remote = socket.create_connection((self.host, port), timeout=5)
            client.setblocking(False); remote.setblocking(False)
            with self.lock: self.active.update((client, remote))
            self.callback('connected', '')
            sockets = [client, remote]
            while not self.stop_event.is_set():
                readable, _, _ = select.select(sockets, [], [], .5)
                for src in readable:
                    data = src.recv(65536)
                    if not data: return
                    dst = remote if src is client else client
                    # Use a bounded timeout so stop can interrupt a stalled peer.
                    dst.settimeout(5); dst.sendall(data); dst.setblocking(False)
        except (OSError, ValueError) as exc:
            if not self.stop_event.is_set(): self.callback('relay_error', str(exc))
        finally:
            with self.lock:
                self.active.discard(client)
                if remote: self.active.discard(remote)
            client.close()
            if remote: remote.close()

    def stop(self):
        self.stop_event.set()
        with self.lock: game_id = self.last_game; sockets = list(self.active)
        if self.udp and game_id is not None:
            try: self.udp.sendto(cancel_packet(game_id), (self.broadcast_host, self.broadcast_port))
            except OSError: pass
        for item in sockets + [self.udp, self.listener]:
            if item:
                try: item.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                item.close()
        for thread in self.threads:
            if thread is not threading.current_thread(): thread.join(timeout=.7)
