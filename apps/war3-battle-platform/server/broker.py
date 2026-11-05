"""Self-hosted rendezvous and byte relay for War3 Battle Platform.

Production connections require TLS. The loopback-only plaintext mode exists
solely for development and integration testing.
"""
import argparse
import asyncio
import base64
import json
import secrets
import ssl
import struct
import time

MAX_LINE = 8192
MAX_PEERS = 128
MAX_RELAYS = 128
HEARTBEAT_TIMEOUT = 45


def packet_info(encoded):
    try:
        packet = base64.b64decode(encoded, validate=True)
        if not 44 <= len(packet) <= 1400 or packet[:2] != b'\xf7\x30' or struct.unpack_from('<H', packet, 2)[0] != len(packet): return None
        if packet[4:8] not in (b'PX3W', b'3RAW') or not 21 <= struct.unpack_from('<I', packet, 8)[0] <= 29: return None
        if b'\0' not in packet[20:-22] or not struct.unpack_from('<H', packet, len(packet)-2)[0]: return None
        return {'packet': encoded, 'game_id': struct.unpack_from('<I', packet, 12)[0], 'edition': packet[4:8].decode('ascii'), 'version': struct.unpack_from('<I', packet, 8)[0]}
    except (ValueError, TypeError, struct.error): return None


class Broker:
    def __init__(self):
        self.peers = {}; self.tickets = {}; self.servers = []; self.instance_id = secrets.token_hex(6)

    async def start(self, host, port, ssl_context=None, *, sock=None):
        args = {'sock':sock} if sock is not None else {'host':host, 'port':port}
        server = await asyncio.start_server(self.handle, **args, ssl=ssl_context, limit=MAX_LINE, ssl_handshake_timeout=10 if ssl_context else None)
        self.servers.append(server); return server

    @staticmethod
    async def send(writer, data):
        writer.write(json.dumps(data, separators=(',', ':')).encode() + b'\n')
        await asyncio.wait_for(writer.drain(), timeout=10)

    async def broadcast(self):
        lobbies = [{'host': key, **p['advertisement']} for key, p in self.peers.items() if p['advertisement']]
        for key, peer in list(self.peers.items()):
            try: await self.send(peer['writer'], {'type':'lobbies', 'lobbies':[entry for entry in lobbies if entry['host'] != key], 'peers':len(self.peers)})
            except (OSError, ConnectionError, asyncio.TimeoutError): peer['writer'].close()

    async def handle(self, reader, writer):
        peer_id = None
        try:
            first = await self.read(reader, 10)
            if first.get('type') == 'hello':
                if len(self.peers) >= MAX_PEERS: return
                peer_id = secrets.token_hex(16)
                self.peers[peer_id] = {'writer':writer, 'advertisement':None}
                await self.send(writer, {'type':'welcome', 'id':peer_id, 'server_id':self.instance_id})
                await self.broadcast()
                await self.peer_loop(peer_id, reader, writer)
            elif first.get('type') == 'attach':
                await self.attach(first, reader, writer)
        except (ValueError, OSError, ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            pass
        finally:
            if peer_id and self.peers.pop(peer_id, None): await self.broadcast()
            writer.close()
            try: await writer.wait_closed()
            except (OSError, ConnectionError): pass

    @staticmethod
    async def read(reader, timeout):
        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not line or len(line) > MAX_LINE or not line.endswith(b'\n'): raise ValueError('Invalid frame')
        data = json.loads(line)
        if not isinstance(data, dict): raise ValueError('Invalid message')
        return data

    async def peer_loop(self, peer_id, reader, writer):
        while True:
            msg = await self.read(reader, HEARTBEAT_TIMEOUT)
            peer = self.peers[peer_id]
            if msg.get('type') == 'ping':
                await self.send(writer, {'type':'pong'})
            elif msg.get('type') == 'publish':
                ad = packet_info(msg.get('packet'))
                if not ad:
                    await self.send(writer, {'type':'publish_rejected'}); continue
                if ad != peer['advertisement']:
                    peer['advertisement'] = ad; await self.broadcast()
                await self.send(writer, {'type':'publish_ack', 'game_id':ad['game_id']})
            elif msg.get('type') == 'withdraw':
                if peer['advertisement']:
                    peer['advertisement'] = None; await self.broadcast()
            elif msg.get('type') == 'connect':
                host = self.peers.get(msg.get('host'))
                if not host or host is peer or not host['advertisement']:
                    await self.send(writer, {'type':'unavailable', 'request':msg.get('request')}); continue
                now = time.monotonic()
                for token, state in list(self.tickets.items()):
                    if state['expires'] < now: self.tickets.pop(token, None)
                if len(self.tickets) >= MAX_RELAYS:
                    await self.send(writer, {'type':'unavailable', 'request':msg.get('request')}); continue
                token = secrets.token_hex(24); host_secret = secrets.token_hex(24); join_secret = secrets.token_hex(24)
                self.tickets[token] = {'expires':now + 15, 'host_secret':host_secret, 'join_secret':join_secret, 'host':None, 'join':None, 'ready':asyncio.Event()}
                await self.send(host['writer'], {'type':'incoming', 'ticket':token, 'secret':host_secret})
                await self.send(writer, {'type':'outgoing', 'ticket':token, 'secret':join_secret, 'request':msg.get('request')})
            else: raise ValueError('Invalid request')

    async def attach(self, msg, reader, writer):
        state = self.tickets.get(msg.get('ticket'))
        side = msg.get('side')
        if not state or state['expires'] < time.monotonic() or side not in ('host','join'): return
        if not secrets.compare_digest(str(msg.get('secret','')), state[side+'_secret']) or state[side] is not None: return
        state[side] = (reader, writer)
        if state['host'] and state['join']: state['ready'].set()
        try: await asyncio.wait_for(state['ready'].wait(), timeout=15)
        except asyncio.TimeoutError: self.tickets.pop(msg.get('ticket'), None); return
        if side == 'host':
            self.tickets.pop(msg.get('ticket'), None)
            host_reader, host_writer = state['host']; join_reader, join_writer = state['join']
            tasks = []
            try:
                await self.send(host_writer, {'type':'ready'}); await self.send(join_writer, {'type':'ready'})
                async def copy(source, destination):
                    while True:
                        chunk = await asyncio.wait_for(source.read(65536), timeout=180)
                        if not chunk: return
                        destination.write(chunk); await asyncio.wait_for(destination.drain(), timeout=15)
                tasks = [asyncio.create_task(copy(host_reader, join_writer)), asyncio.create_task(copy(join_reader, host_writer))]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    try: task.result()
                    except (OSError, ConnectionError, asyncio.TimeoutError): pass
            finally:
                for task in tasks: task.cancel()
                state['ready'].clear(); join_writer.close()
        else:
            # The host-side handler owns the paired streams until closure.
            while state['ready'].is_set() and not writer.is_closing(): await asyncio.sleep(.2)

    async def close(self):
        for peer in self.peers.values(): peer['writer'].close()
        for server in self.servers: server.close(); await server.wait_closed()


def main():
    parser = argparse.ArgumentParser(description='War3 LAN lobby directory and relay')
    parser.add_argument('--host', default='127.0.0.1'); parser.add_argument('--port', type=int, default=47653)
    parser.add_argument('--cert'); parser.add_argument('--key'); parser.add_argument('--insecure-loopback', action='store_true')
    args = parser.parse_args()
    if args.insecure_loopback:
        if args.host not in ('127.0.0.1', '::1', 'localhost'): parser.error('Plaintext is permitted only on loopback.')
        context = None
    else:
        if not args.cert or not args.key: parser.error('TLS certificate and key are required.')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(args.cert, args.key)
    async def run():
        broker = Broker(); server = await broker.start(args.host, args.port, context)
        print(f'Listening on {args.host}:{args.port}', flush=True)
        async with server: await server.serve_forever()
    asyncio.run(run())

if __name__ == '__main__': main()
