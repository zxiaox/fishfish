"""Classic LAN names must survive publication and port rewriting byte for byte."""
import base64
import importlib.util
from pathlib import Path
import struct
import unittest

network_spec=importlib.util.spec_from_file_location('war3_multilingual_network',Path('apps/war3-battle-platform/network.py'))
network=importlib.util.module_from_spec(network_spec); network_spec.loader.exec_module(network)
broker_spec=importlib.util.spec_from_file_location('war3_multilingual_broker',Path('apps/war3-battle-platform/server/broker.py'))
broker=importlib.util.module_from_spec(broker_spec); broker_spec.loader.exec_module(broker)


def announcement(name):
    data=bytearray(b'\xf7\x30\0\0PX3W'+struct.pack('<III',27,123,0)+name+b'\0'+bytes(21)+struct.pack('<H',6112))
    struct.pack_into('<H',data,2,len(data)); return bytes(data)


class MultilingualWarcraftTests(unittest.TestCase):
    def test_lobby_names_preserved_in_utf8_and_legacy_codepages(self):
        samples=(('en','Battle','cp1252'),('zh','中文房间','gb18030'),('ja','日本語','cp932'),
                 ('ko','한국어','cp949'),('th','ภาษาไทย','cp874'),('de','Größe','cp1252'),('es','Málaga','cp1252'))
        for language,name,encoding in samples:
            for codec in ('utf-8',encoding):
                with self.subTest(language=language,codec=codec):
                    original=announcement(name.encode(codec))
                    self.assertEqual(network.parse_announcement(original,'TFT',27,language)[2],name)
                    encoded=base64.b64encode(original).decode('ascii')
                    accepted=broker.packet_info(encoded)
                    self.assertIsNotNone(accepted)
                    restored=base64.b64decode(accepted['packet'])
                    forwarded=network.rewrite_port(restored,43210)
                    self.assertEqual(forwarded[:-2],original[:-2])
                    self.assertEqual(network.parse_announcement(forwarded,'TFT',27,language)[2],name)
                    self.assertEqual(struct.unpack_from('<H',forwarded,len(forwarded)-2)[0],43210)

if __name__=='__main__': unittest.main()
