import tempfile
import unittest
from datetime import date
from pathlib import Path

from befrienders_tester.registry import DuplicateCodes, Registry, filter_registered
from befrienders_tester.roster import read_roster
from tests.helpers import roster_xlsx, sample_people

W = (date(2026, 11, 1), date(2026, 11, 4))


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'sub' / 'registry.sqlite'
        self.registry = Registry(self.path)

    def test_register_then_detect_and_persist_across_instances(self):
        people = sample_people(20)
        batch = self.registry.register([p.code for p in people[:10]], 'day 1')
        self.assertEqual(batch, 1)
        again = Registry(self.path)  # a new process / next day
        self.assertEqual(again.total_codes(), 10)
        known = again.known([p.code for p in people])
        self.assertEqual(set(known), {p.code for p in people[:10]})

    def test_next_day_upload_rejects_only_the_repeated_rows(self):
        people = sample_people(30)
        self.registry.register([p.code for p in people[:20]], 'day 1')
        accepted, errors = filter_registered(people, self.registry)
        self.assertEqual([p.code for p in accepted], [p.code for p in people[20:]])
        self.assertEqual(len(errors), 20)
        self.assertIn('مكرر', errors[0])
        self.assertIn('#1', errors[0])

    def test_same_roster_file_twice_is_fully_rejected(self):
        people = sample_people(15)
        rows = [(p.name, p.birth_date, p.gov) for p in people]
        data = roster_xlsx(rows)
        first, _ = read_roster(data, *W)
        self.registry.register([p.code for p in first])
        second, errors = read_roster(data, *W)
        accepted, dup_errors = filter_registered(second, self.registry)
        self.assertEqual((accepted, len(dup_errors)), ([], 15))

    def test_register_is_atomic_and_refuses_duplicates(self):
        people = sample_people(6)
        self.registry.register([p.code for p in people[:3]])
        with self.assertRaises(DuplicateCodes):
            self.registry.register([people[2].code, people[4].code])
        self.assertEqual(self.registry.total_codes(), 3)  # the clean code was not half-registered

    def test_delete_batch_and_clear(self):
        people = sample_people(6)
        first = self.registry.register([p.code for p in people[:3]])
        self.registry.register([p.code for p in people[3:]])
        self.registry.delete_batch(first)
        self.assertEqual(self.registry.total_codes(), 3)
        self.assertEqual(self.registry.known([people[0].code]), {})
        self.registry.clear()
        self.assertEqual((self.registry.total_codes(), self.registry.batches()), (0, []))

    def test_stores_codes_only(self):
        people = sample_people(3)
        self.registry.register([p.code for p in people])
        blob = self.path.read_bytes()
        self.assertTrue(all(p.name.encode() not in blob for p in people))


class GenderColumnTests(unittest.TestCase):
    def test_gender_column_is_read(self):
        data = roster_xlsx([('كريم علي محمد حسن', date(1977, 7, 20), 'ز', 'ذكر'),
                            ('منى علي محمد حسن', date(1985, 2, 3), 'ق', 'أنثى')])
        people, errors = read_roster(data, *W)
        self.assertEqual((errors, [p.gender for p in people]), ([], ['ذكر', 'أنثى']))

    def test_partial_or_invalid_gender_is_reported(self):
        data = roster_xlsx([('كريم علي محمد حسن', date(1977, 7, 20), 'ز', 'ذكر'),
                            ('منى علي محمد حسن', date(1985, 2, 3), 'ق', ''),
                            ('هبة علي محمد حسن', date(1986, 2, 3), 'ق', 'غير معروف')])
        people, errors = read_roster(data, *W)
        self.assertEqual(len(people), 1)
        self.assertEqual(len(errors), 2)

    def test_no_gender_column_still_works(self):
        people, errors = read_roster(roster_xlsx([('كريم علي محمد حسن', date(1977, 7, 20), 'ز')]), *W)
        self.assertEqual((errors, people[0].gender), ([], ''))


if __name__ == '__main__':
    unittest.main()
