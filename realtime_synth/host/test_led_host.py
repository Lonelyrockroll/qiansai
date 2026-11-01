import unittest,threading
from unittest.mock import Mock
from protocol import Decoder,packet,RESPONSE_SYNC,LED_CONTROL,LED_STATUS
from server import Controller
class LedHostTests(unittest.TestCase):
 def test_led_status_has_own_feedback_and_no_audio_rate_field(self):
  payload=bytearray(20);payload[1]=3;payload[2]=31;payload[3]=2;payload[4]=6;payload[5]=8
  payload[6:10]=(1<<31).to_bytes(4,'little');payload[10:14]=(123).to_bytes(4,'little');payload[18]=17;payload[19]=19
  raw=RESPONSE_SYNC+packet(1,128,payload)[2:]
  c=Controller.__new__(Controller);c.seq=0;c.decoder=Decoder();c.transport=Mock();c.transport.read.return_value=raw
  c.feedback={'firmware':17,'amp_muted':True};c.led_feedback={}
  status=c._exchange(LED_STATUS)
  self.assertEqual(status['latched_mask'],1<<31);self.assertEqual(status['frames'],123)
  self.assertIs(c.led_feedback,status);self.assertEqual(c.feedback,{'firmware':17,'amp_muted':True})
 def test_only_four_modes_and_version_guard(self):
  c=Controller.__new__(Controller);c.lock=threading.RLock();c.transport=object();c.feedback={'firmware':17}
  c.exchange=Mock();c.snapshot=Mock(return_value={})
  for mode in (0,1,2,3):
   c.exchange.reset_mock();c.action(dict(action='led',mode=mode))
   self.assertEqual([x.args for x in c.exchange.call_args_list],[(LED_CONTROL,bytes([mode])),(LED_STATUS,)])
  for mode in (-1,4,True,1.0,'1'):
   with self.assertRaises(ValueError):c.action(dict(action='led',mode=mode))
  c.feedback={'firmware':16}
  with self.assertRaises(ValueError):c.action(dict(action='led',mode=1))
 def test_v18_pin_mode_and_exit_before_normal_lights(self):
  from protocol import LED_PIN_CONTROL
  c=Controller.__new__(Controller);c.lock=threading.RLock();c.transport=object();c.feedback={'firmware':18}
  c.exchange=Mock();c.snapshot=Mock(return_value={})
  for mode in (0,1,2):
   c.exchange.reset_mock();c.action(dict(action='led_pin',mode=mode))
   self.assertEqual([x.args for x in c.exchange.call_args_list],[(LED_PIN_CONTROL,bytes([mode])),(LED_STATUS,)])
  for mode in (3,-1,True,'2',2.0):
   with self.assertRaises(ValueError):c.action(dict(action='led_pin',mode=mode))
  c.exchange.reset_mock();c.action(dict(action='led',mode=1))
  self.assertEqual([x.args for x in c.exchange.call_args_list],[(LED_PIN_CONTROL,b'\0'),(LED_CONTROL,b'\1'),(LED_STATUS,)])
  c.feedback={'firmware':17}
  with self.assertRaises(ValueError):c.action(dict(action='led_pin',mode=2))
if __name__=='__main__':unittest.main()
