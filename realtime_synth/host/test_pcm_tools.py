import array,json,struct,tempfile,threading,time,unittest,wave,zlib
from pathlib import Path
import pcm_tools
from protocol import PCM_STATUS,PCM_READ,PCM_CONTROL,packet,Decoder

class FakeController:
    def __init__(self,bad=None):
        self.lock=threading.RLock();self.transport=object();self.feedback={'firmware':19}
        self.pcm_job={};self.pcm_context={};self.pcm_feedback={};self.pcm_files={};self.bad=bad
        self.params={};self.keyboard={};self.gain_mode=0
        self.data=struct.pack('<17h',*range(-8,9))
        self.meta=dict(ready=True,error=False,capture_id=5,count=17,first_frame=123,crc32=zlib.crc32(self.data),firmware=19)
    def exchange(self,op,p=b''):
        if op==PCM_STATUS:return self.meta.copy()
        if op==PCM_CONTROL:return {}
        ident,offset,count=struct.unpack('<HHB',p)
        data=self.data[2*offset:2*(offset+count)]
        if self.bad=='data':data=bytes([data[0]^1])+data[1:]
        return dict(capture_id=ident,offset=offset+(self.bad=='offset'),count=count,data=data.hex())

class Tests(unittest.TestCase):
    def test_frozen_capture_not_replaced_or_accidentally_canceled(self):
        c=FakeController();calls=[];call=c.exchange
        def logged(op,p=b''):
            calls.append(op)
            if op==PCM_CONTROL:c.meta.update(ready=False,armed=False,recording=False);return {}
            return call(op,p)
        c.exchange=logged
        with self.assertRaises(ValueError):pcm_tools.arm(c,64,'immediate',0)
        with self.assertRaises(ValueError):pcm_tools.abort(c)
        with self.assertRaises(ValueError):pcm_tools.release_ready(c,4)
        self.assertNotIn(PCM_CONTROL,calls)
        c.pcm_files={'pcm':'already-exported.pcm'};pcm_tools.release_ready(c,5)
        self.assertEqual(calls.count(PCM_CONTROL),1);self.assertEqual(c.pcm_files['pcm'],'already-exported.pcm')
    def run_export(self,bad=None):
        c=FakeController(bad);pcm_tools.start_export(c)
        deadline=time.monotonic()+3
        while c.pcm_job['running'] and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(c.pcm_job['running']);return c
    def test_raw_bytes_crc_and_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            pcm_tools.OUTPUT=Path(tmp);c=self.run_export()
            self.assertTrue(c.pcm_job['done']);self.assertEqual(c.pcm_job['progress'],17)
            with wave.open(c.pcm_files['raw']) as w:self.assertEqual(w.readframes(100),c.data)
            meta=json.loads(Path(c.pcm_job['metadata_path']).read_text(encoding='utf8'))
            self.assertTrue(meta['verified']);self.assertEqual(meta['first_frame'],123)
    def test_corrupted_data_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            pcm_tools.OUTPUT=Path(tmp);c=self.run_export('data')
            self.assertFalse(c.pcm_job['done']);self.assertIn('CRC32',c.pcm_job['error']);self.assertFalse(list(Path(tmp).iterdir()))
    def test_wrong_offset_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            pcm_tools.OUTPUT=Path(tmp);c=self.run_export('offset')
            self.assertFalse(c.pcm_job['done']);self.assertFalse(list(Path(tmp).iterdir()))
    def test_validation_and_export_lock(self):
        c=FakeController()
        for n in (0,32769,True,1.5):
            with self.assertRaises(ValueError):pcm_tools.arm(c,n,'nonzero',0)
        c.pcm_job={'running':True}
        with self.assertRaises(ValueError):pcm_tools.arm(c,17,'nonzero',0)
    def test_wire_decoder_signed_samples(self):
        p=bytearray(20);p[1:3]=(5).to_bytes(2,'little');p[3:5]=(12).to_bytes(2,'little');p[5]=2
        p[6:10]=struct.pack('<hh',-32768,32767);p[18:]=bytes([19,23])
        wire=b'\x5a\xa5'+packet(3,128,p)[2:]
        result=Decoder().feed(wire)[0]
        self.assertEqual(result['offset'],12);self.assertEqual(bytes.fromhex(result['data']),p[6:10])

if __name__=='__main__':unittest.main()
