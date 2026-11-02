from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'realtime_synth/host'))
from fx_tools import FIELDS,LEGACY_PRESETS,PRESETS,configure,validate
from protocol import Decoder,FX_STATUS,RESPONSE_SYNC,packet


class Device:
    transport=True
    feedback={'firmware':32}
    def __init__(self,profile):
        self.fx_feedback={'effect_profile':profile,'monitor_mute':True}
        self.commands=[]
    def exchange(self,op,payload=b''):
        self.commands.append((op,payload))


class EffectProfiles(unittest.TestCase):
    def test_both_firmware_profiles_and_muted_monitor(self):
        for version,table in [(1,LEGACY_PRESETS),(2,PRESETS)]:
            for name,preset in table.items():
                device=Device(version)
                configure(device,{'preset':name})
                expected=dict(preset,monitor_mute=1)
                self.assertEqual(device.commands[0][1],bytes(expected[k] for k in FIELDS))
                self.assertEqual(device.commands[1][0],FX_STATUS)
                validate(preset,version)
        with self.assertRaises(ValueError):validate(PRESETS['reverb'],1)
        with self.assertRaises(ValueError):validate(dict(PRESETS['combined'],delay_mix=65),2)

    def test_capability_bit_is_decoded_without_changing_version(self):
        for flag,expected in [(0,1),(64,2)]:
            payload=bytearray(20);payload[10]=flag;payload[18]=32;payload[19]=FX_STATUS
            wire=RESPONSE_SYNC+packet(7,128,bytes(payload))[2:]
            value=Decoder().feed(wire)[0]
            self.assertEqual(value['effect_profile'],expected)
            self.assertFalse(value['clipped'])
            self.assertFalse(value['monitor_mute'])


if __name__=='__main__':unittest.main()
