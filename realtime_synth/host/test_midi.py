import struct
import unittest
from unittest.mock import Mock

from protocol import Decoder,MIDI_STATUS,PANIC,packet,keyboard_payload
from server import Controller


def reply(payload):
    payload=bytearray(payload);payload[18:20]=bytes([33,MIDI_STATUS])
    return b'\x5a\xa5'+packet(9,128,payload)[2:]


class MidiTests(unittest.TestCase):
    def test_status_and_extended_diagnostics(self):
        data=bytearray(20);data[1:5]=bytes([3,31,4,5])
        struct.pack_into('<IIHHB',data,5,0x12345678,0x10203040,3,2,61)
        value=Decoder().feed(reply(data))[0]
        self.assertEqual((value['mode'],value['bytes'],value['events'],value['last_note']),(3,0x12345678,0x10203040,61))
        self.assertEqual((value['framing_errors'],value['overflows']),(3,2))
        self.assertTrue(value['session'] and value['ready'] and value['sustain'] and value['rx_high'])
        data=bytearray(20);data[1]=128|100;data[2]=2
        struct.pack_into('<HHHB',data,3,5,7,8,6)
        value=Decoder().feed(reply(data))[0]
        self.assertEqual((value['last_velocity'],value['last_channel'],value['sustain_channels'],value['ignored_offs'],value['steals'],value['sounding']),(100,3,5,7,8,6))

    def test_midi_mode_requires_new_firmware(self):
        self.assertEqual(keyboard_payload(mode=3)[0],3)
        controller=Controller();controller.stop.set();controller.worker.join()
        controller.feedback={'firmware':32}
        with self.assertRaises(ValueError):controller.set_keyboard({'mode':3})

    def test_detaching_pc_keeps_offline_midi_alive(self):
        for mode in (0,2,3):
            controller=Controller();controller.stop.set();controller.worker.join()
            controller.feedback={'firmware':33};controller.display_feedback={'mode':mode}
            transport=Mock();controller.transport=transport;controller.exchange=Mock()
            controller.disconnect()
            transport.close.assert_called_once()
            controller.exchange.assert_called_once_with(PANIC,b'\x02')

    def test_poll_does_not_overwrite_main_audio_status(self):
        class Transport:
            def write(self,request):
                payload=bytearray(20);payload[1]=3
                raw=bytearray(reply(payload));raw[3]=request[3];raw[26]=0
                for byte in raw[2:26]:raw[26]^=byte
                self.data=bytes(raw)
            def read(self):data=self.data;self.data=b'';return data
            def close(self):pass
        controller=Controller();controller.stop.set();controller.worker.join()
        controller.transport=Transport();controller.feedback={'firmware':33,'active':2}
        controller.exchange(MIDI_STATUS)
        self.assertEqual(controller.feedback,{'firmware':33,'active':2})
        self.assertEqual(controller.midi_feedback['mode'],3)
        controller.transport=None


if __name__=='__main__':unittest.main()
