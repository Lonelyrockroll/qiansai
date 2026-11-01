"""Verify v26 virtual-piano packets against the physical 32-key layout."""
import struct,unittest
from protocol import CONFIG,FS,WHITE_KEYS
from server import Controller

class WhiteKeyTests(unittest.TestCase):
    def controller(self,firmware=26):
        c=Controller.__new__(Controller);c.keyboard={'mode':0};c.next_voice=19
        c.release_until={};c.notes={};c.feedback=dict(firmware=firmware,amp_hold=True,amp_ready=True)
        c.params=dict(timbre=4,level=.1,attack_ms=2,decay_ms=800,sustain=0,release_ms=100)
        self.writes=[];c.exchange=lambda op,data:self.writes.append((op,data))
        return c

    def test_all_32_keys_use_pitch_not_voice_for_display(self):
        c=self.controller()
        for i,n in enumerate(WHITE_KEYS):
            c.note_on(n);op,b=self.writes[-1]
            self.assertEqual((op,b[1],b[17]),(CONFIG,1,0x80|i))
            self.assertEqual(struct.unpack_from('<I',b,5)[0],round(440*2**((n-69)/12)*2**32/FS))
        self.assertEqual(len(c.notes),32)
        for i in reversed(range(32)):
            c.note_off(WHITE_KEYS[i]);self.assertEqual((self.writes[-1][1][1],self.writes[-1][1][17]),(0,0x80|i))
        self.assertFalse(c.notes)
    def test_either_side_and_black_keys_rejected(self):
        c=self.controller()
        for n in [35,37,39,42,44,46,58,90,91]:
            with self.assertRaises(ValueError):c.note_on(n)
        self.assertEqual(self.writes,[])
    def test_raw_engineering_tone_and_older_firmware(self):
        c=self.controller();c.configure(7,1,355);self.assertEqual(len(self.writes[-1][1]),17)
        c=self.controller(25);c.note_on(61);self.assertEqual(len(self.writes[-1][1]),17)
if __name__=='__main__':unittest.main()
