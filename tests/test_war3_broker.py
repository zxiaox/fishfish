import asyncio
import base64
import importlib.util
import json
import struct
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('war3_broker', Path('apps/war3-battle-platform/server/broker.py'))
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def packet(port=6112):
    data = bytearray(b'\xf7\x30\0\0PX3W' + struct.pack('<III', 26, 123, 0) + b'Test\0' + bytes(21) + struct.pack('<H', port))
    struct.pack_into('<H', data, 2, len(data)); return base64.b64encode(data).decode()


class BrokerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.broker = mod.Broker(); self.server = await self.broker.start('127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]; self.writers = []

    async def asyncTearDown(self):
        for writer in self.writers: writer.close()
        await self.broker.close()

    async def connection(self):
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        self.writers.append(writer); return reader, writer

    async def send(self, writer, msg):
        writer.write(json.dumps(msg).encode()+b'\n'); await writer.drain()

    async def receive(self, reader, kind):
        while True:
            line = await asyncio.wait_for(reader.readline(), 3)
            self.assertTrue(line)
            msg = json.loads(line)
            if msg['type'] == kind: return msg

    async def test_directory_and_relay_between_two_clients(self):
        hr, hw = await self.connection(); jr, jw = await self.connection()
        await self.send(hw, {'type':'hello'}); host = await self.receive(hr, 'welcome')
        await self.send(jw, {'type':'hello'}); await self.receive(jr, 'welcome')
        await self.send(hw, {'type':'publish', 'packet':packet()})
        acknowledgement = await self.receive(hr, 'publish_ack')
        self.assertEqual(acknowledgement['game_id'], 123)
        lobby = await self.receive(jr, 'lobbies')
        while not lobby['lobbies']: lobby = await self.receive(jr, 'lobbies')
        self.assertEqual(lobby['lobbies'][0]['host'], host['id'])
        self.assertEqual(lobby['peers'], 2)
        await self.send(jw, {'type':'connect','host':host['id'],'request':'abc'})
        incoming = await self.receive(hr, 'incoming'); outgoing = await self.receive(jr, 'outgoing')
        host_data_r, host_data_w = await self.connection(); join_data_r, join_data_w = await self.connection()
        await self.send(host_data_w, {'type':'attach','ticket':incoming['ticket'],'secret':incoming['secret'],'side':'host'})
        await self.send(join_data_w, {'type':'attach','ticket':outgoing['ticket'],'secret':outgoing['secret'],'side':'join'})
        await self.receive(host_data_r,'ready'); await self.receive(join_data_r,'ready')
        join_data_w.write(b'game-request'); await join_data_w.drain()
        self.assertEqual(await asyncio.wait_for(host_data_r.readexactly(12),3), b'game-request')
        host_data_w.write(b'game-reply'); await host_data_w.drain()
        self.assertEqual(await asyncio.wait_for(join_data_r.readexactly(10),3), b'game-reply')
        await self.send(hw, {'type':'withdraw'})
        change = await self.receive(jr,'lobbies')
        self.assertEqual(change['lobbies'], [])

    async def test_bad_publication_is_reported_without_disconnect(self):
        reader, writer = await self.connection()
        await self.send(writer, {'type':'hello'})
        welcome = await self.receive(reader, 'welcome')
        self.assertTrue(welcome['server_id'])
        await self.send(writer, {'type':'publish','packet':'invalid'})
        await self.receive(reader, 'publish_rejected')
        await self.send(writer, {'type':'ping'})
        await self.receive(reader, 'pong')

    def test_advertisement_validation(self):
        self.assertIsNotNone(mod.packet_info(packet()))
        self.assertIsNone(mod.packet_info('not base64'))
        self.assertIsNone(mod.packet_info(base64.b64encode(b'bad').decode()))

if __name__ == '__main__': unittest.main()
