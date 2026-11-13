import unittest
from datetime import date

from befrienders_tester.codes import governorate_code, name_letters, split_name
from befrienders_tester.roster import read_roster
from tests.helpers import roster_xlsx

W = (date(2026, 11, 1), date(2026, 11, 4))


class CodeTests(unittest.TestCase):
    def test_user_example(self):
        self.assertEqual(name_letters('كريم علي محمد حسن'), (('ك', 'ع', 'م'), ('س', 'ن')))

    def test_compound_abd_is_one_name(self):
        self.assertEqual(split_name('احمد عبد الله محمود عبد الرحمن'),
                         ['احمد', 'عبد الله', 'محمود', 'عبد الرحمن'])
        self.assertEqual(name_letters('احمد عبد الله محمود عبد الرحمن'), (('ا', 'ع', 'م'), ('م', 'ن')))

    def test_letter_normalisation(self):
        # hamza forms -> ا ; ة -> ه ; ى -> ي
        self.assertEqual(name_letters('أحمد إيمان آدم فاطمة'), (('ا', 'ا', 'ا'), ('م', 'ه')))
        self.assertEqual(name_letters('مصطفى منى علي موسى'), (('م', 'م', 'ع'), ('س', 'ي')))

    def test_trailing_hamza_is_skipped(self):
        self.assertEqual(name_letters('علي محمد حسن بهاء'), (('ع', 'م', 'ح'), ('ه', 'ا')))
        self.assertEqual(name_letters('علي محمد حسن ضياء'), (('ع', 'م', 'ح'), ('ي', 'ا')))

    def test_bad_names(self):
        for bad in ('علي محمد حسن', 'علي محمد حسن احمد محمود', 'Ali Mohamed Hassan Ahmed', 'علي محمد حسن ن'):
            with self.assertRaises(ValueError):
                name_letters(bad)

    def test_governorate(self):
        self.assertEqual(governorate_code('الجيزة'), 'ز')
        self.assertEqual(governorate_code('القاهره'), 'ق')
        self.assertEqual(governorate_code(' ز '), 'ز')
        with self.assertRaises(ValueError):
            governorate_code('مدينة غير معروفة')


class RosterTests(unittest.TestCase):
    def test_reads_with_header_and_formats(self):
        data = roster_xlsx([('كريم علي محمد حسن', date(1977, 7, 20), 'ز'),
                            ('سمير ياسر هاني وليد', '15/03/1990', 'القاهرة'),
                            ('طارق عمرو خالد ايمن', '٠٥/٠٦/١٩٨٥', 'ق')])
        people, errors = read_roster(data, *W)
        self.assertEqual(errors, [])
        self.assertEqual([p.code for p in people],
                         ['20 07 77 ز ك ع م س ن', '15 03 90 ق س ي ه ي د', '05 06 85 ق ط ع خ م ن'])

    def test_without_header(self):
        people, errors = read_roster(roster_xlsx([('كريم علي محمد حسن', date(1977, 7, 20), 'ز')], header=False), *W)
        self.assertEqual((len(people), errors), (1, []))
        self.assertEqual(people[0].row, 1)

    def test_row_errors_are_reported_with_row_numbers(self):
        data = roster_xlsx([('كريم علي محمد حسن', date(1977, 7, 20), 'ز'),
                            ('كريم علي محمد حسن', date(1977, 7, 20), 'ز'),       # duplicate code
                            ('علي محمد حسن', date(1980, 1, 1), 'ز'),               # three parts
                            ('سمير ياسر هاني وليد', date(2015, 1, 1), 'ز'),        # too young
                            ('خالد عمرو نبيل صلاح', date(1950, 1, 1), 'ز'),        # too old
                            ('عادل ماجد بهاء شريف', 'غير مفهوم', 'ز'),             # bad date
                            ('رضا جمال سعيد فتحي', date(1990, 1, 1), 'مكان')])    # bad governorate
        people, errors = read_roster(data, *W)
        self.assertEqual(len(people), 1)
        self.assertEqual(len(errors), 6)
        self.assertTrue(errors[0].startswith('صف 3') and 'مكرر' in errors[0])
        self.assertTrue(all(e.startswith('صف ') for e in errors))

    def test_age_limits_are_18_to_50(self):
        rows = [('كريم علي محمد حسن', date(2010, 11, 5), 'ز'),    # 16 on 1/11/2026 -> rejected
                ('سمير ياسر هاني وليد', date(2009, 12, 1), 'ز'),   # 16 -> rejected
                ('طارق عمرو خالد ايمن', date(2008, 11, 1), 'ز'),   # exactly 18 on 1/11/2026 -> accepted
                ('عادل ماجد بهاء شريف', date(1976, 11, 5), 'ز'),   # 50 on 4/11/2026 -> accepted
                ('رضا جمال سعيد فتحي', date(1975, 11, 3), 'ز')]    # turns 51 on 3/11/2026 -> rejected
        people, errors = read_roster(roster_xlsx(rows), *W)
        self.assertEqual([p.name for p in people], ['طارق عمرو خالد ايمن', 'عادل ماجد بهاء شريف'])
        self.assertEqual(len(errors), 3)
        self.assertTrue(all('18' in e for e in errors))

    def test_corrupt_file(self):
        people, errors = read_roster(b'not an xlsx', *W)
        self.assertEqual(people, [])
        self.assertEqual(len(errors), 1)


if __name__ == '__main__':
    unittest.main()
