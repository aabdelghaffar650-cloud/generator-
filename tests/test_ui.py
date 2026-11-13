"""Streamlit tests: page loads; full flow; a second upload of the same names is rejected."""
import os
import tempfile
import unittest
from pathlib import Path

APP = str(Path(__file__).resolve().parents[1] / 'app.py')

try:
    from streamlit.testing.v1 import AppTest
    import streamlit as st
except Exception:  # streamlit missing
    AppTest = None

from datetime import date

from tests.helpers import roster_xlsx, sample_people


class _Upload:
    def __init__(self, data): self.data = data
    def getvalue(self): return self.data


@unittest.skipIf(AppTest is None, 'streamlit not installed')
class UiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ['BEFRIENDERS_REGISTRY'] = str(Path(self.tmp.name) / 'registry.sqlite')
        self.addCleanup(os.environ.pop, 'BEFRIENDERS_REGISTRY', None)
        self.original_uploader = st.file_uploader
        self.addCleanup(setattr, st, 'file_uploader', self.original_uploader)

    def _upload(self, people):
        data = roster_xlsx([(p.name, p.birth_date, p.gov, 'ذكر') for p in people])
        st.file_uploader = lambda *a, **k: _Upload(data)

    def _run(self):
        return AppTest.from_file(APP, default_timeout=60).run()

    def test_page_loads_and_generate_is_disabled_without_roster(self):
        at = self._run()
        self.assertFalse(at.exception, at.exception)
        generate = [b for b in at.button if 'توليد' in b.label]
        self.assertTrue(generate and generate[0].disabled)

    def test_generate_register_then_duplicate_upload_is_rejected(self):
        people = sample_people(25)
        self._upload(people)
        at = self._run()
        self.assertFalse(at.exception, at.exception)
        at.selectbox(key='fill_name').select('سمر')
        at.text_input(key='fill_area').set_value('الدقي البحوث')
        [b for b in at.button if 'تطبيق' in b.label][0].click()
        at.run()
        [b for b in at.button if 'توليد' in b.label][0].click()
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any('نجح التحقق' in x.value for x in at.success))
        [b for b in at.button if 'تسجيل الدفعة' in b.label][0].click()
        at.run()
        self.assertTrue(any('الدفعة مسجّلة' in x.value for x in at.success))

        # the next day: the same 25 names plus 5 new ones -> only the repeated 25 are rejected
        newcomers = sample_people(30, seed=99)
        known = {p.code for p in people}
        fresh = [p for p in newcomers if p.code not in known][:5]
        self._upload(people + fresh)
        again = self._run()
        self.assertFalse(again.exception, again.exception)
        self.assertTrue(any('25 صف مرفوض' in w.value for w in again.warning), [w.value for w in again.warning])
        self.assertTrue(any('تمت قراءة 5 مستفيد' in x.value for x in again.success), [x.value for x in again.success])

    def test_optional_people_counts_in_the_ui(self):
        self._upload(sample_people(55))
        at = self._run()
        at.selectbox(key='fill_name').select('سمر')
        at.text_input(key='fill_area').set_value('الدقي البحوث')
        [b for b in at.button if 'تطبيق على الأيام الفارغة' in b.label][0].click()
        at.run()
        at.number_input(key='syr_55').set_value(4500)
        at.number_input(key='syr_people_55').set_value(55)
        at.number_input(key='con_55').set_value(480)
        at.number_input(key='con_people_55').set_value(30)
        at.run()
        at.number_input(key='lub_people_55').set_value(20)
        at.run()
        [b for b in at.button if 'توليد' in b.label][0].click()
        at.run()
        self.assertFalse(at.exception, at.exception)
        self.assertTrue(any('نجح التحقق' in x.value for x in at.success), [e.value for e in at.error])
        m = at.session_state['report'].metrics
        self.assertEqual((m['syringes'], m['condoms'], m['condom_recipients'], m['lubricant_recipients']), (4500, 480, 30, 20))

    def test_lubricant_people_needs_condom_people(self):
        self._upload(sample_people(10))
        at = self._run()
        self.assertTrue(at.number_input(key='lub_people_10').disabled)

    def _key(self, prefix, name):
        return f'{prefix}_{name}_2026-11-01_2026-11-04'

    def test_multiselect_days_per_outreach_feed_the_schedule(self):
        self._upload(sample_people(24))
        at = self._run()
        d = lambda day: date(2026, 11, day)
        at.multiselect(key=self._key('ms', 'احمد عبد الناصر')).select(d(1)).select(d(3))
        at.text_input(key=self._key('area', 'احمد عبد الناصر')).set_value('حدائق الاهرام')
        at.multiselect(key=self._key('ms', 'سمر')).select(d(2))
        at.text_input(key=self._key('area', 'سمر')).set_value('الدقي البحوث')
        at.multiselect(key=self._key('ms', 'هند')).select(d(4))
        at.text_input(key=self._key('area', 'هند')).set_value('هرم كراته')
        at.run()
        [b for b in at.button if 'تطبيق على جدول الأيام' in b.label][0].click()
        at.run()
        self.assertFalse(at.exception, at.exception)
        [b for b in at.button if 'توليد' in b.label][0].click()
        at.run()
        self.assertFalse(at.exception, at.exception)
        ops = at.session_state['ops']
        self.assertEqual(len(ops), 24)
        expected = {1: ('احمد عبد الناصر', 'حدائق الاهرام'), 2: ('سمر', 'الدقي البحوث'),
                    3: ('احمد عبد الناصر', 'حدائق الاهرام'), 4: ('هند', 'هرم كراته')}
        for op in ops:
            self.assertEqual((op.visit.outreach_name, op.visit.area), expected[op.visit.visit_date.day])
        self.assertTrue(all(o.visit.syringes in (30, 60, 90, 120, 150) for o in ops))

    def test_same_day_for_two_outreach_is_a_conflict(self):
        self._upload(sample_people(10))
        at = self._run()
        at.multiselect(key=self._key('ms', 'سمر')).select(date(2026, 11, 2))
        at.multiselect(key=self._key('ms', 'هند')).select(date(2026, 11, 2))
        at.run()
        self.assertTrue(any('أيام مكررة' in e.value for e in at.error), [e.value for e in at.error])
        apply = [b for b in at.button if 'تطبيق على جدول الأيام' in b.label][0]
        self.assertTrue(apply.disabled)


if __name__ == '__main__':
    unittest.main()
