import unittest
import struct
from protocol import Decoder, packet, voice_payload, response_for_test, FS, keyboard_payload
import server

class FakeTransport:
    def __init__(self):self.reply=b'';self.closed=False;self.commands=0;self.flags=8
    def write(self,data):
        assert data[:2]==b'\xa5\x5a' and len(data)==28
        self.commands+=data[4] in (2,3,5,6)
        if data[4]==6:self.flags=128|16
        if data[4]==3 and data[6]==0:self.flags=8
        self.reply=response_for_test(data[3],data[4],commands=self.commands,flags=self.flags)
    def read(self):
        result=self.reply[:3];self.reply=self.reply[3:];return result
    def close(self):self.closed=True

class FirmwareTransport(FakeTransport):
    def __init__(self,firmware):
        super().__init__();self.firmware=firmware
    def write(self,data):
        super().write(data)
        raw=bytearray(self.reply);op=data[4];raw[24]=self.firmware
        if op in (30,31):
            raw[6:24]=bytes(18)
            if op==30:
                struct.pack_into('<H',raw,7,1577);raw[9]=2
            else:
                raw[7]=3;raw[8]=2
                struct.pack_into('<HHHHI',raw,9,84,12,125,2400,1<<14)
        raw[26]=0
        for b in raw[2:26]:raw[26]^=b
        self.reply=bytes(raw)

class Tests(unittest.TestCase):
    def test_keyboard_payload_and_source_exclusion(self):
        values=struct.unpack('<BBB8H',keyboard_payload(2,31,params=dict(timbre=4,level=.9,attack_ms=1,decay_ms=1000,sustain=0,release_ms=110)))
        self.assertEqual(values[:3],(2,31,4));self.assertLessEqual(values[3],16384)
        for args in [dict(mode=3),dict(key=32),dict(press=128,release=128),dict(sensitivity=0),dict(key=1.2)]:
            with self.assertRaises(ValueError):keyboard_payload(**args)
        ctl=server.Controller();ctl.stop.set();ctl.worker.join();ctl.transport=FakeTransport()
        ctl.keyboard['mode']=1
        with self.assertRaises(ValueError):ctl.note_on(60)
        with self.assertRaises(ValueError):ctl.action(dict(action='spectrum'))
        ctl.disconnect()
    def test_packet_layout(self):
        payload=voice_payload(7,1,440,2,0.5,5,80,0.65,100)
        voice,gate,timbre,level,step,a,d,s,r=struct.unpack('<BBBH I HHHH',payload)
        self.assertEqual((voice,gate,timbre),(7,1,2));self.assertAlmostEqual(step*FS/2**32,440,places=4)
        self.assertTrue(all(1<=x<=65535 for x in (a,d,r)))
        raw=packet(255,2,payload);self.assertEqual(len(raw),28)
        checksum=0
        for b in raw[2:26]:checksum^=b
        self.assertEqual(raw[26],checksum)
    def test_fragment_and_resync(self):
        decoder=Decoder();bad=bytearray(response_for_test(3,4));bad[26]^=1
        raw=b'garbage'+bytes(bad)+response_for_test(4,4,active=32,pcm=-123)
        answers=[]
        for byte in raw:answers+=decoder.feed(bytes([byte]))
        self.assertEqual(len(answers),1);self.assertEqual(answers[0]['seq'],4)
        self.assertEqual(answers[0]['pcm'],-123);self.assertEqual(answers[0]['sample_rate'],FS)
    def test_bounds(self):
        for kwargs in [dict(frequency=float('nan')),dict(frequency=4000),dict(level=2),dict(attack_ms=-1)]:
            args=dict(voice=0,gate=1,frequency=440);args.update(kwargs)
            with self.assertRaises(ValueError):voice_payload(**args)
        piano=voice_payload(0,1,440,timbre=4,sustain=0,release_ms=110)
        self.assertGreater(struct.unpack('<BBBH I HHHH',piano)[-1],1)
        with self.assertRaises(ValueError):voice_payload(0,1,3045,timbre=4)
    def test_gain_and_amp_status(self):
        status=Decoder().feed(response_for_test(8,5,flags=(2<<5)|8))[0]
        self.assertEqual(status['gain_mode'],2);self.assertTrue(status['amp_muted']);self.assertFalse(status['amp_ready'])
        ctl=server.Controller();ctl.stop.set();ctl.worker.join();ctl.transport=FakeTransport()
        ctl.set_gain(2);self.assertEqual(ctl.gain_mode,2)
        with self.assertRaises(ValueError):ctl.set_gain(3)
        ctl.disconnect()
    def test_voice_assignment_and_release(self):
        ctl=server.Controller();ctl.stop.set();ctl.worker.join();ctl.transport=FakeTransport()
        ctl.begin_performance()
        for note in (60,64,67,72):ctl.note_on(note)
        self.assertEqual(len(ctl.notes),4)
        self.assertEqual(len({v['voice'] for v in ctl.notes.values()}),4)
        ctl.note_on(60);self.assertEqual(len(ctl.notes),4)
        ctl.note_off(64);self.assertNotIn(64,ctl.notes)
        reserved=set(ctl.release_until);ctl.note_on(65)
        self.assertNotIn(ctl.notes[65]['voice'],reserved)
        ctl.panic();self.assertFalse(ctl.notes)
        ctl.disconnect();self.assertIsNone(ctl.transport)
    def test_wrong_firmware_is_not_connected(self):
        ctl=server.Controller();ctl.stop.set();ctl.worker.join();fake=FakeTransport()
        def wrong(data):
            raw=bytearray(response_for_test(data[3],data[4]));raw[24]=99
            raw[26]=0
            for b in raw[2:26]:raw[26]^=b
            fake.reply=bytes(raw)
        fake.write=wrong;ctl.transport=fake
        with self.assertRaises(OSError):ctl.exchange(1)
        self.assertIsNone(ctl.transport);self.assertTrue(fake.closed)

    def test_v27_to_v30_main_status(self):
        for version in range(27,31):
            ctl=server.Controller();ctl.stop.set();ctl.worker.join();ctl.transport=FirmwareTransport(version)
            try:
                answer=ctl.exchange(1)
                self.assertEqual(answer['firmware'],version);self.assertEqual(answer['sample_rate'],FS)
            finally:ctl.disconnect()

    def test_actual_v30_decoded_trim_and_guide_status_without_rate(self):
        ctl=server.Controller();ctl.stop.set();ctl.worker.join();ctl.transport=FirmwareTransport(30)
        try:
            main=ctl.exchange(4)
            trim=ctl.exchange(30)
            self.assertEqual((trim['pt_bias'],trim['pt_mode']),(1577,2));self.assertNotIn('sample_rate',trim)
            guide=ctl.exchange(31)
            self.assertTrue(guide['guide_valid'] and guide['guide_playing'])
            self.assertEqual((guide['guide_count'],guide['guide_index'],guide['guide_time_cs'],guide['guide_duration_cs']),(84,12,125,2400))
            self.assertEqual(guide['guide_mask'],1<<14);self.assertNotIn('sample_rate',guide)
            self.assertIs(ctl.feedback,main)
        finally:ctl.disconnect()

    def test_unknown_version_and_bad_rate_still_fail(self):
        for version in (5,27,31,99):
            ctl=server.Controller();ctl.stop.set();ctl.worker.join();fake=FirmwareTransport(version);ctl.transport=fake
            with self.assertRaises(OSError):ctl.exchange(30)
            self.assertIsNone(ctl.transport);self.assertTrue(fake.closed)
        ctl=server.Controller();ctl.stop.set();ctl.worker.join();fake=FirmwareTransport(30)
        normal=fake.write
        def bad_rate(data):
            normal(data);raw=bytearray(fake.reply);raw[20:24]=bytes(4);raw[26]=0
            for b in raw[2:26]:raw[26]^=b
            fake.reply=bytes(raw)
        fake.write=bad_rate;ctl.transport=fake
        with self.assertRaises(OSError):ctl.exchange(4)
        self.assertIsNone(ctl.transport)

if __name__=='__main__':unittest.main()
