import importlib.util
import queue
import socket
import struct
import threading
import time
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('war3_network', Path('apps/war3-battle-platform/network.py'))
network = importlib.util.module_from_spec(spec); spec.loader.exec_module(network)


def announcement(port, version=26, game_id=123):
    # Minimal W3GS_GAMEINFO fixture with a name and fixed-size footer.
    data = bytearray(b'\xf7\x30\0\0PX3W' + struct.pack('<III', version, game_id, 0) + b'Test\0' + bytes(21) + struct.pack('<H', port))
    struct.pack_into('<H', data, 2, len(data))
    return bytes(data)


class WarcraftTests(unittest.TestCase):
    def test_packet_validation_and_port_rewrite(self):
        self.assertEqual(network.search_packet('TFT', 26), b'\xf7\x2f\x10\0PX3W\x1a\0\0\0\0\0\0\0')
        packet = announcement(6113)
        self.assertEqual(network.parse_announcement(packet, 'TFT', 26), (123, 6113, 'Test'))
        self.assertEqual(network.parse_announcement(network.rewrite_port(packet, 12345), 'TFT', 26)[1], 12345)
        for packet_bad in (packet[:10], packet[:-1], packet[:4] + b'BAD!' + packet[8:]):
            with self.assertRaises(ValueError): network.parse_announcement(packet_bad, 'TFT', 26)
        with self.assertRaises(ValueError): network.parse_announcement(packet, 'TFT', 27)

    def test_local_discovery_and_tcp_relay(self):
        host_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); host_udp.bind(('127.0.0.1', 0)); host_udp.settimeout(5)
        local_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); local_udp.bind(('127.0.0.1', 0)); local_udp.settimeout(5)
        host_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM); host_tcp.bind(('127.0.0.1', 0)); host_tcp.listen(); host_tcp.settimeout(5)
        received = queue.Queue(); errors = queue.Queue()
        def host():
            try:
                data, client = host_udp.recvfrom(1024)
                self.assertEqual(data, network.search_packet('TFT', 26))
                host_udp.sendto(announcement(host_tcp.getsockname()[1]), client)
                conn, _ = host_tcp.accept()
                with conn:
                    received.put(conn.recv(1024)); conn.sendall(b'game-reply')
            except Exception as exc: errors.put(exc)
        thread = threading.Thread(target=host, daemon=True); thread.start()
        bridge = network.Bridge('127.0.0.1', 'TFT', 26, lambda *args: None, discovery_port=host_udp.getsockname()[1], broadcast_host='127.0.0.1', broadcast_port=local_udp.getsockname()[1])
        try:
            bridge.start()
            data, _ = local_udp.recvfrom(2048)
            self.assertEqual(network.parse_announcement(data, 'TFT', 26)[1], bridge.proxy_port)
            with socket.create_connection(('127.0.0.1', bridge.proxy_port), timeout=5) as client:
                client.sendall(b'game-request'); self.assertEqual(client.recv(1024), b'game-reply')
            self.assertEqual(received.get(timeout=5), b'game-request')
            thread.join(timeout=5)
            if not errors.empty(): raise errors.get()
        finally:
            bridge.stop(); host_udp.close(); local_udp.close(); host_tcp.close()

if __name__ == '__main__': unittest.main()
