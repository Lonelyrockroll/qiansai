import unittest
from protocol import Decoder, packet, RESPONSE_SYNC, PMOD_STATUS
from touch_logic import hit_test,menu_names

class ModuleTests(unittest.TestCase):
    def test_telemetry_includes_measured_period(self):
        payload=bytearray(20)
        payload[1:3]=bytes([3,0x80])
        payload[3:5]=(5208).to_bytes(2,'little')
        payload[5:7]=(323).to_bytes(2,'little')
        payload[7:9]=(2).to_bytes(2,'little')
        payload[18:20]=bytes([22,PMOD_STATUS])
        response=Decoder().feed(RESPONSE_SYNC+packet(9,128,payload)[2:])[0]
        self.assertEqual((response['baud'],response['commands'],response['dropped']),(9601,323,2))
        self.assertTrue(response['locked'] and response['testing'])
        self.assertEqual(response['lamps'],128)

    def test_effect_menu_on_both_pages_and_old_firmware(self):
        for drums in (True,False):
            rows=menu_names(dict(firmware=22,drum_mode=drums))
            self.assertEqual(rows[8],'效果切换')
            self.assertEqual(hit_test(700,525,rows=len(rows)),8)
            self.assertIsNone(hit_test(700,540,rows=len(rows)))
            rows=menu_names(dict(firmware=21,drum_mode=drums))
            self.assertIsNone(hit_test(700,525,rows=len(rows)))
if __name__=='__main__':unittest.main()
