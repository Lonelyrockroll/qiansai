import unittest
from unittest.mock import Mock
from protocol import Decoder,packet,RESPONSE_SYNC,OUTPUT_GAIN_STATUS
from server import Controller
class GainStatusTests(unittest.TestCase):
 def test_real_schema_keeps_audio_feedback(self):
  p=bytearray(20);p[1]=4;p[2]=1;p[3]=1;p[4:7]=(32768).to_bytes(3,'little');p[7:11]=(12345).to_bytes(4,'little');p[11:13]=(28000).to_bytes(2,'little');p[13:15]=(16384).to_bytes(2,'little');p[15:17]=(5244).to_bytes(2,'little');p[18]=21;p[19]=27
  c=Controller.__new__(Controller);c.seq=0;c.decoder=Decoder();c.transport=Mock();c.transport.read.return_value=RESPONSE_SYNC+packet(1,128,p)[2:];c.feedback={'firmware':21,'amp_muted':True};c.output_gain_feedback={}
  s=c._exchange(OUTPUT_GAIN_STATUS)
  self.assertEqual((s['melodic_factor'],s['limiter_gain_q16'],s['limited_frames'],s['ceiling']),(4,32768,12345,28000))
  self.assertEqual(s['keyboard_level'],16384);self.assertTrue(s['limited']);self.assertFalse(s['limiter_overrun']);self.assertEqual(c.feedback,{'firmware':21,'amp_muted':True});self.assertIs(c.output_gain_feedback,s)
if __name__=='__main__':unittest.main()
