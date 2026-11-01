"""Gesture edge cases + actual captured HID replay + controller forwarding guards."""
import json,time,unittest
import threading
from pathlib import Path
from unittest.mock import Mock
from touch_logic import ContactFrames,TapDetector,to_pixel,hit_test
from server import Controller
from protocol import DISPLAY_ACTION,DISPLAY_STATUS,STATUS,KEY_STATUS

def contact(x=800,y=280,down=True,id=0):
    return dict(x=x,y=y,x_min=0,x_max=1024,y_min=0,y_max=600,down=down,id=id)

class GestureTests(unittest.TestCase):
    def test_geometry(self):
        self.assertEqual(to_pixel(contact(1024,600)),(1023,599))
        self.assertIsNone(hit_test(631,140));self.assertEqual(hit_test(632,112),0)
        self.assertIsNone(hit_test(992,140));self.assertIsNone(hit_test(800,157))
        self.assertEqual(hit_test(800,480),7);self.assertIsNone(hit_test(800,500))
        with self.assertRaises(ValueError):to_pixel(contact(1050,0))
    def test_release_once(self):
        t=TapDetector()
        for i in range(30):self.assertIsNone(t.feed([contact()],i*.02))
        self.assertEqual(t.feed([contact(down=False)],.62),3)
        for i in range(4):self.assertIsNone(t.feed([contact(down=False)],.64+i*.02))
    def test_drag_multitouch_long_press(self):
        sequences=[[(contact(),0),(contact(800,330),.1),(contact(800,330,False),.2)],
                   [(contact(),0),(contact(),3),(contact(down=False),3.1)]]
        for seq in sequences:
            t=TapDetector()
            for c,now in seq:self.assertIsNone(t.feed([c],now))
        t=TapDetector();t.feed([contact()],0)
        self.assertIsNone(t.feed([contact(),contact(id=1)],.1))
        self.assertIsNone(t.feed([contact(down=False),contact(down=False,id=1)],.2))
        t.feed([contact()],.4);self.assertEqual(t.feed([contact(down=False)],.6),3)
    def test_focus_loss_and_missing_release(self):
        t=TapDetector();t.feed([contact()],0);t.feed([], .1,allowed=False)
        self.assertIsNone(t.feed([contact(down=False)],.2))
        t.feed([contact()],.3);self.assertIsNone(t.feed([contact(down=False)],1.5))
    def test_hybrid_contacts_and_pattern(self):
        f=ContactFrames();t=TapDetector()
        self.assertIsNone(f.feed(dict(time=0,contact_count=3,contacts=[contact()])))
        self.assertIsNone(f.feed(dict(time=0,contact_count=0,contacts=[contact(down=False,id=1)])))
        frame=f.feed(dict(time=0,contact_count=0,contacts=[contact(down=False,id=2)]))
        t.feed(frame,0);self.assertEqual(t.feed([contact(down=False)],.2),3)
        t=TapDetector();t.feed([contact(20,20)],0,pattern=True)
        self.assertEqual(t.feed([contact(20,20,False)],.2,pattern=True),7)
    def test_recorded_hid_replay(self):
        from touch_hid import enumerate_touch_devices
        devices=enumerate_touch_devices();self.assertEqual(len(devices),1)
        path=Path(__file__).resolve().parents[1]/'control_display/touch_validation/probe_events.jsonl'
        f=ContactFrames();t=TapDetector();count=0;clicks=[]
        for line in path.read_text(encoding='utf8').splitlines():
            e=json.loads(line)
            if 'raw_hex' not in e:continue
            decoded=devices[0].decode(bytes.fromhex(e['raw_hex']))
            self.assertEqual(decoded['contacts'],e['contacts']);count+=1
            frame=f.feed(dict(time=e['time'],**decoded))
            if frame is not None:
                click=t.feed(frame,e['time'])
                if click is not None:clicks.append(click)
        self.assertGreater(count,100);self.assertEqual(clicks,[])

class ControllerTests(unittest.TestCase):
    def make(self):
        c=Controller.__new__(Controller);c.touch_session='test';c.touch=dict(enabled=True,active=True);c.keypad=dict(enabled=False,active=False)
        c.feedback=dict(firmware=11);c.transport=object();c.exchange=Mock();c.panic=Mock();return c
    def test_atomic_command(self):
        c=self.make();c.touch_click(dict(session='test',index=3))
        self.assertEqual(c.exchange.call_args_list[0].args,(DISPLAY_ACTION,bytes([5,3])))
        self.assertEqual([x.args[0] for x in c.exchange.call_args_list],[DISPLAY_ACTION,DISPLAY_STATUS,STATUS,KEY_STATUS])
        self.assertEqual(c.touch['last_menu'],3)
    def test_invalid_or_stale(self):
        for row in [-1,8,True,1.5,'3']:
            c=self.make()
            with self.assertRaises(ValueError):c.touch_click(dict(session='test',index=row))
            c.exchange.assert_not_called()
        c=self.make()
        with self.assertRaises(ValueError):c.touch_click(dict(session='old',index=0))
        c.touch['active']=False
        with self.assertRaises(ValueError):c.touch_click(dict(session='test',index=0))
    def test_focus_loss_mutes(self):
        c=self.make();c.touch_heartbeat(dict(session='test',active=False,reports=20,taps=1))
        c.panic.assert_called_once();self.assertFalse(c.touch['active'])
    def test_dead_bridge_mutes_even_with_browser_alive(self):
        c=self.make();c.touch_seen=time.monotonic()-4;c.ui_seen=time.monotonic();c.last_poll=time.monotonic()
        c.lock=threading.RLock();c.stop=Mock();c.stop.wait.side_effect=[False,True]
        c.monitor()
        c.panic.assert_called_once();self.assertFalse(c.touch['enabled'])

if __name__=='__main__':unittest.main(verbosity=2)
