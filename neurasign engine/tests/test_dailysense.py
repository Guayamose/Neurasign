from pathlib import Path
import sys
import unittest
import io
import tempfile
import zipfile
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from neurasign_engine import dailysense_data as data


class DailySenseTests(unittest.TestCase):
    def test_partial_archive_cannot_yield_truncated_member(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as z:
            z.writestr('nested.zip',b'example'*100)
        raw=stream.getvalue()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            info=z.getinfo('nested.zip')
        member={'member':info.filename,'header_offset':info.header_offset,'compressed_bytes':info.compress_size,
                'bytes':info.file_size,'crc32':f'{info.CRC:08x}'}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.part';path.write_bytes(raw[:100])
            self.assertIsNone(data.member_bytes(path,member))
            path.write_bytes(raw)
            self.assertEqual(data.member_bytes(path,member),b'example'*100)
            damaged=bytearray(raw);damaged[45]^=1;path.write_bytes(damaged)
            with self.assertRaises(ValueError):
                data.member_bytes(path,member)

    def test_daily_cutoff_excludes_future_minute(self):
        frame=pd.DataFrame({channel:np.ones(100) for channel in data.SIGNALS});frame['minute']=np.arange(100)
        first,count,_=data.summarize_day(frame,0,60*60)
        frame.loc[frame.minute>=60,data.SIGNALS]=999
        changed,second,_=data.summarize_day(frame,0,60*60)
        self.assertEqual(count,60);self.assertEqual(second,60)
        self.assertEqual(first,changed)

    def test_history_uses_previous_days_only(self):
        frame=pd.DataFrame({name:np.arange(5,dtype=float) for name in data.BASE_FEATURES})
        frame['date']=pd.date_range('2020-01-01',periods=5).strftime('%Y-%m-%d');frame['participant']='p'
        before=data.add_history(frame);frame.loc[4,data.BASE_FEATURES]=999
        after=data.add_history(frame)
        cols=[f+'__past7_delta' for f in data.BASE_FEATURES]
        np.testing.assert_allclose(before.loc[3,cols].to_numpy(float),after.loc[3,cols].to_numpy(float))

    def test_profile_excludes_reference_and_context(self):
        for columns in data.PROFILES.values():
            self.assertFalse(set(columns)&{'rating','participant','date','unit_id','row_id','drm_vas1'})
            self.assertTrue(all(name.startswith(('day__','last60__')) for name in columns))

    def test_minute_native_coverage(self):
        result=data.minute_statistics(np.full(120,60.),0,1.)
        np.testing.assert_allclose(result['mean'],[60,60])
        result=data.minute_statistics(np.full(20,60.),0,1.)
        self.assertTrue(result['mean'].isna().all())

    def test_empty_native_signal_files_are_missing_not_zero(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('IBI.csv','')
            archive.writestr('HR.csv','')
        result=data.summarize_recording(stream.getvalue())
        self.assertTrue(result.empty)

    def test_bad_channel_is_missing_and_healthy_channel_survives(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('HR.csv','0\n1\n'+'60\n'*60)
            archive.writestr('EDA.csv','0\n4\n'+'1\n'*240)
        raw=bytearray(stream.getvalue())
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            item=archive.getinfo('EDA.csv');offset=item.header_offset+30+len(item.filename)
        raw[offset+8]^=1
        frame,audit=data.summarize_recording(bytes(raw),return_audit=True)
        self.assertEqual(frame.hr_mean.iloc[0],60)
        self.assertTrue(frame.eda_mean.isna().all())
        self.assertEqual([a['channel'] for a in audit if not a['accepted']],['EDA.csv'])


if __name__=='__main__':
    unittest.main()
