"""Hierarchical UI wire compatibility and page-aware, release-only touch control."""
import unittest
import threading
from unittest.mock import Mock, patch

from protocol import ARM, Decoder, DISPLAY_ACTION, DISPLAY_STATUS, KEY_STATUS, NAVIGATION, STATUS, packet, response_for_test
from server import Controller, NavigationChanged
from touch_logic import TapDetector, hit_test, menu_names, navigation_enabled


def navigation(page=0,cursor=0,**kwargs):
    value=dict(supported=True,revision=1,epoch=10,page=page,cursor=cursor,row_count=5 if page==4 else 6,
               confirm=False,monitor_open=False,score_visible=False,pending=False)
    value.update(kwargs)
    return value


def response(seq,page=0,cursor=0,status=0,flags=0,revision=1,epoch=10):
    p=bytearray(20)
    p[:7]=bytes([status,page,cursor,flags,5 if page==4 else 6,0,revision])
    p[7]=epoch
    p[18:20]=bytes([32,NAVIGATION])
    return b'\x5a\xa5'+packet(seq,128,p)[2:]


def contact(down=True):
    return dict(x=750,y=382,x_min=0,x_max=1023,y_min=0,y_max=599,down=down,id=1)


class WireTests(unittest.TestCase):
    def test_decode_revision_and_flags(self):
        d=Decoder();results=[]
        for b in response(9,page=3,cursor=5,flags=15):results+=d.feed(bytes([b]))
        self.assertEqual(len(results),1);r=results[0]
        self.assertTrue(navigation_enabled(r));self.assertEqual((r['page'],r['cursor'],r['row_count']),(3,5,6))
        self.assertEqual(r['epoch'],10)
        for flag in ('confirm','monitor_open','score_visible','pending'):self.assertTrue(r[flag])
        self.assertNotIn('sample_rate',r)

    def test_unknown_revision_or_malformed_shape_does_not_enable_hits(self):
        for kwargs in [dict(revision=2),dict(page=6),dict(page=4,cursor=5),dict(status=2)]:
            self.assertFalse(navigation_enabled(Decoder().feed(response(1,**kwargs))[0]))

    def test_optional_probe_does_not_disconnect_old_v32(self):
        class OldV32:
            closed=False
            def write(self,data):
                raw=bytearray(response_for_test(data[3],data[4],status=2,active=3));raw[24]=32
                raw[26]=0
                for b in raw[2:26]:raw[26]^=b
                self.reply=bytes(raw)
            def read(self):r=self.reply;self.reply=b'';return r
            def close(self):self.closed=True
        c=Controller();c.stop.set();c.worker.join();device=OldV32();c.transport=device
        c.feedback=dict(firmware=32,active=3)
        result=c.exchange(NAVIGATION)
        self.assertFalse(result['supported']);self.assertIs(c.transport,device);self.assertFalse(device.closed)
        self.assertEqual(c.feedback,dict(firmware=32,active=3))
        with self.assertRaises(ValueError):c.exchange(NAVIGATION,b'\x02')
        self.assertIs(c.transport,device);self.assertFalse(device.closed)
        c.transport=None

    def test_busy_command_preserves_navigation_capability(self):
        class Busy:
            def write(self,data):self.reply=response(data[3],page=1,status=4)
            def read(self):r=self.reply;self.reply=b'';return r
        c=Controller();c.stop.set();c.worker.join();c.transport=Busy()
        c.navigation_feedback=navigation(1)
        with self.assertRaises(ValueError):c.exchange(NAVIGATION,b'\x02')
        self.assertTrue(navigation_enabled(c.navigation_feedback));self.assertIsNotNone(c.transport)
        c.transport=None

    def test_reconnect_reprobes_and_clears_previous_capability(self):
        c=Controller();c.stop.set();c.worker.join()
        version=[32];supports=[True];probe_versions=[];cache_at_hello=[]
        def exchange(op,payload=b''):
            if op==1:
                cache_at_hello.append(c.navigation_feedback.copy())
                return dict(firmware=version[0],gain_mode=1)
            if op==DISPLAY_STATUS:return dict(timbre=4)
            if op==27:return dict(keyboard_level=16384)
            if op==NAVIGATION:
                probe_versions.append(version[0])
                c.navigation_feedback=navigation(supported=supports[0])
                return c.navigation_feedback
            return {}
        c.exchange=Mock(side_effect=exchange)
        with patch('server.list_devices',return_value=([dict(id='test')],[])),patch('server.open_device',side_effect=lambda _:Mock()):
            c.connect('test');self.assertTrue(navigation_enabled(c.navigation_feedback))
            supports[0]=False
            c.connect('test');self.assertFalse(navigation_enabled(c.navigation_feedback))
            version[0]=31
            c.connect('test');self.assertEqual(c.navigation_feedback,{})
        self.assertEqual(probe_versions,[32,32]);self.assertEqual(cache_at_hello,[{},{},{}])
        c.disconnect()


class GestureTests(unittest.TestCase):
    def test_all_pages_use_only_visible_rows(self):
        for page in range(6):
            nav=navigation(page)
            self.assertEqual(len(menu_names({},nav)),nav['row_count'])
            for i in range(nav['row_count']):
                self.assertEqual(hit_test(672,330+36*i,navigation=nav),i)
                self.assertEqual(hit_test(999,365+36*i,navigation=nav),i)
            self.assertIsNone(hit_test(671,330,navigation=nav))
            self.assertIsNone(hit_test(1000,330,navigation=nav))
            self.assertIsNone(hit_test(700,330+36*nav['row_count'],navigation=nav))
        self.assertEqual(menu_names({},navigation(3,confirm=True))[5],'再次确认清空')

    def test_overlays_block_hidden_controls(self):
        for key in ('monitor_open','score_visible','pending'):
            self.assertIsNone(hit_test(750,380,navigation=navigation(**{key:True})))
        self.assertEqual(hit_test(20,20,pattern=True,navigation=navigation()),7)

    def test_page_or_confirmation_transition_cancels_touch(self):
        for new in (navigation(1),navigation(0,cursor=1),navigation(0,epoch=11),navigation(0,confirm=True),navigation(0,monitor_open=True)):
            t=TapDetector();t.feed([contact()],0,navigation=navigation())
            self.assertIsNone(t.feed([contact(False)],.1,navigation=new))
        t=TapDetector();t.feed([contact()],0,navigation=navigation(1))
        self.assertEqual(t.feed([contact(False)],.1,navigation=navigation(1)),1)

    def test_old_v32_keeps_flat_geometry(self):
        old=dict(firmware=32)
        self.assertEqual(len(menu_names(old,navigation(supported=False))),13)
        self.assertEqual(hit_test(754,502,rows=13,navigation=navigation(supported=False)),11)


class ControllerTests(unittest.TestCase):
    def make(self,nav=None):
        c=Controller.__new__(Controller);c.touch_session='test';c.touch=dict(enabled=True,active=True)
        c.feedback=dict(firmware=32);c.navigation_feedback=nav or navigation(1)
        c.keyboard=dict(mode=0);c.output_gain_feedback={};c.panic=Mock()
        self.display=dict(firmware=32,pattern=False,focus=0,timbre=4,level=16384)
        self.sheet=dict(score_show=False,score_visible=False,score_loading=False)
        def exchange(op,payload=b''):
            if op==NAVIGATION:
                if payload and payload[0]==1:
                    c.navigation_feedback.update(page=payload[1],cursor=payload[2],epoch=(c.navigation_feedback['epoch']+1)&255)
                return c.navigation_feedback.copy()
            if op==DISPLAY_STATUS:return self.display.copy()
            if op==32:return self.sheet.copy()
            return {}
        c.exchange=Mock(side_effect=exchange)
        return c

    def writes(self,c):return [call.args for call in c.exchange.call_args_list if len(call.args)>1 and call.args[1]]

    def test_tap_selects_exact_timbre_row_then_executes(self):
        c=self.make();c.touch_click(dict(session='test',page=1,index=2,confirm=False,epoch=10))
        self.assertEqual(self.writes(c),[(NAVIGATION,bytes([1,1,2,1,10])),(NAVIGATION,bytes([2,1,11]))])
        self.assertEqual(c.touch['last_name'],'纯净正弦')
        self.assertEqual(c.touch['last_page'],1)

    def test_back_and_second_clear_confirmation(self):
        for page,row,confirm in [(1,0,False),(3,5,True)]:
            c=self.make(navigation(page,row,confirm=confirm))
            c.touch_click(dict(session='test',page=page,index=row,confirm=confirm,epoch=10))
            self.assertEqual(self.writes(c),[(NAVIGATION,bytes([1,page,row,1,10])),(NAVIGATION,bytes([2,1,11]))])

    def test_guard_uses_wrapped_selection_epoch(self):
        c=self.make(navigation(1,epoch=255))
        c.touch_click(dict(session='test',page=1,index=2,epoch=255))
        self.assertEqual(self.writes(c),[(NAVIGATION,bytes([1,1,2,1,255])),(NAVIGATION,bytes([2,1,0]))])

    def test_stale_page_and_stale_confirmation_do_not_execute(self):
        for kwargs in [dict(page=0,confirm=False),dict(page=1,confirm=True)]:
            c=self.make();c.touch_click(dict(session='test',index=2,epoch=10,**kwargs))
            self.assertEqual(self.writes(c),[])
        c=self.make()
        with self.assertRaises(ValueError):c.touch_click(dict(session='test',index=2))
        self.assertEqual(self.writes(c),[])
        c=self.make(navigation(1,epoch=11))
        c.touch_click(dict(session='test',page=1,index=2,epoch=10))
        self.assertEqual(self.writes(c),[])

    def test_hidden_menu_does_not_receive_taps(self):
        for key in ('monitor_open','score_visible','pending'):
            c=self.make(navigation(1,**{key:True}));c.touch_click(dict(session='test',page=1,index=2,epoch=10))
            self.assertEqual(self.writes(c),[])
        c=self.make();self.sheet['score_loading']=True
        c.touch_click(dict(session='test',page=1,index=2,epoch=10));self.assertEqual(self.writes(c),[])

    def test_pattern_exits_only_while_visible(self):
        c=self.make();self.display['pattern']=True
        c.touch_click(dict(session='test',page=1,index=7,pattern=True,epoch=10))
        self.assertEqual(self.writes(c),[(DISPLAY_ACTION,b'\x04')])
        c=self.make();c.touch_click(dict(session='test',page=1,index=7,pattern=True,epoch=10))
        self.assertEqual(self.writes(c),[])

    def test_encoder_wraps_within_current_page(self):
        c=self.make(navigation(4,cursor=0));c.control_function('menu_prev')
        self.assertEqual(self.writes(c),[(NAVIGATION,bytes([1,4,4,1,10]))])
        c=self.make(navigation(1,cursor=5));c.control_function('menu_next')
        self.assertEqual(self.writes(c),[(NAVIGATION,bytes([1,1,0,1,10]))])

    def test_encoder_and_confirm_keep_overlay_priority(self):
        c=self.make(navigation(monitor_open=True));c.control_function('menu_prev',count=2)
        self.assertEqual(self.writes(c),[(DISPLAY_ACTION,b'\x09'),(DISPLAY_ACTION,b'\x09')])
        c=self.make(navigation(monitor_open=True));c.control_function('confirm')
        self.assertEqual(self.writes(c),[(NAVIGATION,bytes([2,1,10]))])

    def test_full_rotation_cancels_confirmation(self):
        c=self.make(navigation(3,5,confirm=True))
        c.control_function('menu_next',count=6)
        self.assertEqual(self.writes(c),[(DISPLAY_ACTION,b'\x01')]*6)

    def test_guard_rejection_does_not_replay_action(self):
        for reject_subcommand in (1,2):
            c=self.make();normal=c.exchange.side_effect
            def racing(op,payload=b''):
                if op==NAVIGATION and payload and payload[0]==reject_subcommand:
                    c.navigation_feedback=navigation(0,0,epoch=12)
                    raise NavigationChanged('simulated physical mute')
                return normal(op,payload)
            c.exchange.side_effect=racing
            c.touch_click(dict(session='test',page=1,index=2,epoch=10))
            self.assertEqual(c.navigation_feedback['page'],0)
            self.assertEqual(c.exchange.call_args_list[-1].args,(NAVIGATION,))
            rejected=[args for args in self.writes(c) if args[0]==NAVIGATION and args[1][0]==reject_subcommand]
            self.assertEqual(len(rejected),1)
            self.assertNotIn('last_menu',c.touch)
            if reject_subcommand==1:
                self.assertFalse(any(args[1][0]==2 for args in self.writes(c)))

    def test_confirmation_defers_during_pdf_upload(self):
        c=self.make(navigation(4,4));self.sheet['score_loading']=True
        c.control_function('confirm')
        self.assertEqual(self.writes(c),[])
        c=self.make(navigation(pending=True));c.control_function('confirm')
        self.assertEqual(self.writes(c),[])

    def test_selection_ack_with_queued_or_hidden_ui_cancels_execution(self):
        for changed in (dict(pending=True),dict(monitor_open=True),dict(score_visible=True),dict(page=0,cursor=0)):
            c=self.make();normal=c.exchange.side_effect
            def queued(op,payload=b''):
                reply=normal(op,payload)
                if op==NAVIGATION and payload and payload[0]==1:
                    c.navigation_feedback.update(changed)
                    reply=c.navigation_feedback.copy()
                return reply
            c.exchange.side_effect=queued
            c.touch_click(dict(session='test',page=1,index=2,epoch=10))
            self.assertEqual(self.writes(c),[(NAVIGATION,bytes([1,1,2,1,10]))])
            self.assertEqual(c.exchange.call_args_list[-1].args,(NAVIGATION,))
            self.assertNotIn('last_menu',c.touch)

    def test_play_shortcut_uses_session_commands_without_legacy_selection(self):
        c=self.make();c.control_function('play_toggle')
        self.assertEqual(self.writes(c),[])
        self.assertTrue(any(call.args==(ARM,) for call in c.exchange.call_args_list))
        c=self.make();self.display['amp_hold']=True;c.control_function('play_toggle')
        c.panic.assert_called_once();self.assertEqual(self.writes(c),[])

    def test_web_display_confirm_uses_guarded_navigation(self):
        c=self.make();c.lock=threading.RLock();c.snapshot=Mock(return_value={})
        c.action(dict(action='display',command=2))
        self.assertEqual(self.writes(c),[(NAVIGATION,bytes([2,1,10]))])

    def test_keypad_confirm_uses_guarded_navigation(self):
        c=self.make();c.keypad_seq=0;c.keypad=dict(enabled=True,active=True,actions=0)
        c.keypad_store=Mock(revision=0,value=dict(bindings={'B_PRESS':dict(action='confirm',step=1)}))
        c.keypad_event(dict(session='test',seq=1,revision=0,input='B_PRESS'))
        self.assertEqual(self.writes(c),[(NAVIGATION,bytes([2,1,10]))])


if __name__=='__main__':unittest.main(verbosity=2)
