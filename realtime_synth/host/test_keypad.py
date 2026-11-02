"""Replay the already verified 18 physical inputs; never synthesize a replacement recording."""
import json,tempfile,unittest,threading,time
from pathlib import Path
from unittest.mock import Mock
from keypad_config import KeypadInterpreter,MappingStore,defaults,validate,INPUTS
from server import Controller
from protocol import DISPLAY_ACTION,DISPLAY_STATUS
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'usb_keypad_1189_8840_check_2026-10-26/physical_mapping_reviewed_20261027.json'
KEYCOL='VID_1189&PID_8840&MI_01&COL01';MOUSECOL='VID_1189&PID_8840&MI_01&COL02'
def key(v,down=True,col=KEYCOL):return dict(type='keyboard',vkey=v,down=down,collection=col)
def wheel(delta=120):return dict(type='wheel',axis='vertical',delta=delta,collection=MOUSECOL)

class InputTests(unittest.TestCase):
    def test_real_18_inputs(self):
        record=json.loads(SOURCE.read_text(encoding='utf8'));result=[]
        for row,expected in zip(record['records'],INPUTS):
            decoder=KeypadInterpreter();seen=[]
            for event in row['events']:seen+=decoder.feed(event,event['elapsed_ms']/1000)
            seen+=decoder.flush(row['events'][-1]['elapsed_ms']/1000+.05)
            # This immutable recording predates the persistent F13 remap.
            wanted=[] if expected=='K12' else [(expected,1)]
            self.assertEqual(seen,wanted,(row['physical_action'],seen))
            result.append(dict(input=expected,events=len(row['events']),decoded=seen))
        (ROOT/'keypad_control').mkdir(exist_ok=True)
        (ROOT/'keypad_control/physical_replay_validation.json').write_text(json.dumps(dict(result='passed',source=str(SOURCE),source_modified=False,records=result),ensure_ascii=False,indent=2),encoding='utf8')
    def test_control_and_combo(self):
        d=KeypadInterpreter();self.assertEqual(d.feed(key(17),0),[]);d.feed(key(17,False),.02)
        self.assertEqual(d.flush(.03),[]);self.assertEqual(d.flush(.08),[])
        d=KeypadInterpreter();d.feed(key(17),0);d.feed(key(17,False),.02)
        self.assertEqual(d.feed(wheel(),.03),[('A_CW',1)]);self.assertEqual(d.flush(.1),[])
        d=KeypadInterpreter();d.feed(key(17,col='VID_1111&PID_2222&MI_01&COL01'),0)
        self.assertEqual(d.feed(wheel(),.02),[('B_CW',1)])
    def test_repeat_filter_and_unknown_devices(self):
        d=KeypadInterpreter();out=[]
        for i in range(100):out+=d.feed(key(70),i*.001)
        self.assertEqual(out,[('K01',1)])
        d.feed(key(70,False),.12);self.assertEqual(d.feed(key(70),.13),[('K01',1)])
        for v in [70,17,44]:self.assertEqual(d.feed(key(v,col='OTHER'),.14),[])
    def test_f13_down_hold_release_and_knob(self):
        d=KeypadInterpreter();out=[]
        for i in range(100):
            t=i*.1
            self.assertEqual(d.feed(key(124),t),[('K12',1)])
            self.assertEqual(d.feed(key(124),t+.001),[])
            d.feed(key(17),t+.002)
            self.assertEqual(d.feed(wheel(120 if i%2 else -120),t+.003),[('A_CW' if i%2 else 'A_CCW',1)])
            self.assertEqual(d.feed(key(17,False),t+.004),[])
            self.assertEqual(d.feed(key(124,False),t+.005),[])
            self.assertEqual(d.flush(t+.08),[])
        d.feed(key(124),20);d.suspend()
        self.assertEqual(d.feed(key(124),20.1),[])
        self.assertEqual(d.feed(key(124,False),20.2),[])
        self.assertEqual(d.feed(key(124),20.3),[('K12',1)])
    def test_suspend_discards_held_prefix(self):
        d=KeypadInterpreter();d.feed(key(17),0);d.suspend()
        self.assertEqual(d.feed(wheel(),.1),[]);d.feed(key(17,False),.2);self.assertEqual(d.flush(.3),[])
        d.feed(key(17),.4);self.assertEqual(d.feed(wheel(-120),.4),[('A_CCW',1)])
    def test_knob_press_and_fractional_wheel(self):
        d=KeypadInterpreter()
        self.assertEqual(d.feed(wheel(60),0),[]);self.assertEqual(d.feed(wheel(60),.01),[('B_CW',1)])
        d.feed(key(17),.02);self.assertEqual(d.feed(wheel(240),.03),[('A_CW',2)])
        for btn,expected in [('Right','A_PRESS'),('Left','B_PRESS')]:
            e=dict(type='mouse_button',button=btn,down=True,collection=MOUSECOL)
            self.assertEqual(d.feed(e,.04),[(expected,1)]);self.assertEqual(d.feed(e,.05),[])
    def test_stress_is_device_local(self):
        d=KeypadInterpreter();out=[]
        for i in range(2000):
            now=i*.1;d.feed(key(17),now);out+=d.feed(wheel(120 if i%2==0 else -120),now+.001);d.feed(key(17,False),now+.002)
            d.feed(key(70,col='OTHER'),now+.003);out+=d.flush(now+.05)
        self.assertEqual(len(out),2000);self.assertFalse(any(k=='K12' for k,_ in out))

class ConfigTests(unittest.TestCase):
    def test_defaults_and_roundtrip(self):
        self.assertEqual(set(validate(defaults())['bindings']),set(INPUTS))
        with tempfile.TemporaryDirectory(prefix='tang_keypad_test_') as folder:
            store=MappingStore(Path(folder)/'mapping.json');value=defaults();value['bindings']['A_CW']['step']=5
            store.save(value);again=MappingStore(store.path);self.assertEqual(again.snapshot(),value)
            bad=defaults();bad['bindings']['K01']['action']='shell_command'
            before=store.path.read_bytes()
            with self.assertRaises(ValueError):store.save(bad)
            self.assertEqual(before,store.path.read_bytes())
    def test_boundaries(self):
        for step in [0,11,True,1.5]:
            v=defaults();v['bindings']['A_CW']['step']=step
            with self.assertRaises(ValueError):validate(v)
        v=defaults();v['bindings'].pop('K12')
        with self.assertRaises(ValueError):validate(v)

class ControllerTests(unittest.TestCase):
    def make(self):
        c=Controller.__new__(Controller);c.touch_session='test';c.keypad_seq=0
        c.keypad=dict(enabled=True,active=True,actions=0);c.keypad_store=MappingStore(ROOT/'keypad_control/absent_test_config.json')
        c.feedback=dict(firmware=12);c.keyboard=dict(mode=0);c.panic=Mock();c.output_gain_feedback={}
        c.exchange=Mock(return_value=dict(focus=0,timbre=4,level=16384));return c
    def test_exact_level_and_selection(self):
        c=self.make();c.control_function('volume_down',2)
        self.assertEqual(c.exchange.call_args_list[1].args,(DISPLAY_ACTION,bytes([7])+int(15073).to_bytes(2,'little')))
        c=self.make();c.control_function('menu_prev',1)
        self.assertEqual(c.exchange.call_args_list[1].args,(DISPLAY_ACTION,b'\x06\x07'))
        c=self.make();c.control_function('tone_next',1)
        self.assertEqual(c.exchange.call_args_list[1].args,(DISPLAY_ACTION,b'\x08\x00'))
    def test_sequence_and_revision_guards(self):
        c=self.make();e=dict(session='test',seq=1,revision=0,input='A_CCW',count=1)
        c.keypad_event(e);n=c.exchange.call_count;c.keypad_event(e);self.assertEqual(c.exchange.call_count,n)
        c.keypad_event(dict(e,seq=2,revision=99));self.assertEqual(c.exchange.call_count,n)
        with self.assertRaises(ValueError):c.keypad_event(dict(e,seq=3,session='old'))
    def test_defaults_printscreen_no_fpga_action(self):
        c=self.make();c.keypad_event(dict(session='test',seq=1,revision=0,input='K09',count=1))
        c.exchange.assert_not_called();self.assertEqual(c.keypad['actions'],0)
    def test_v16_all_keys_are_fixed_drums(self):
        c=self.make();c.feedback=dict(firmware=16,amp_ready=True)
        for i in range(12):c.keypad_event(dict(session='test',seq=i+1,revision=0,input=f'K{i+1:02}',count=1))
        pads=[call.args[1] for call in c.exchange.call_args_list if call.args[0]==15]
        self.assertEqual(pads,[bytes([i]) for i in range(12)])
        c.panic.assert_not_called();self.assertEqual(c.keypad['actions'],12)
    def test_v16_muted_pad_does_not_queue_a_future_hit(self):
        c=self.make();c.feedback=dict(firmware=16,amp_ready=False)
        event=dict(session='test',seq=1,revision=0,input='K01',count=1)
        c.keypad_event(event);c.feedback['amp_ready']=True;c.keypad_event(event)
        c.exchange.assert_not_called();self.assertEqual(c.keypad['actions'],0)

if __name__=='__main__':unittest.main(verbosity=2)
