import random
import unittest
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta

from befrienders_tester.exporter import csv_bytes, visit_record
from befrienders_tester.generator import distribute_exact, generate
from befrienders_tester.model import dump_operations, load_operations
from befrienders_tester.reference_core import age_on, base_cells
from befrienders_tester.rules import ACTORS, OUTREACH_NAMES, syringe_note
from befrienders_tester.validation import validate
from tests.helpers import AREAS, make_settings, sample_people, schedule_for


class SyringeRuleTests(unittest.TestCase):
    def test_note_text(self):
        self.assertEqual(syringe_note(90), '')
        self.assertEqual(syringe_note(30), '')
        self.assertEqual(syringe_note(150), 'المستفيد بيضرب 5 مرات في اليوم')
        self.assertEqual(syringe_note(120), 'المستفيد بيضرب 4 مرات في اليوم')
        self.assertEqual(syringe_note(100), 'المستفيد بيضرب من 3 إلى 4 مرات في اليوم')
        self.assertEqual(syringe_note(110), 'المستفيد بيضرب من 3 إلى 4 مرات في اليوم')

    def test_all_visits_follow_the_rule(self):
        s = make_settings(200, syringes=200 * 90)
        ops = generate(s, sample_people(200))
        self.assertTrue(validate(ops, s).passed)
        quantities = [o.visit.syringes for o in ops]
        self.assertTrue(all(q % 30 == 0 and 30 <= q <= 150 for q in quantities))
        self.assertEqual(set(quantities) - {30, 60, 90, 120, 150}, set())
        self.assertTrue(any(q > 90 for q in quantities) and any(q <= 90 for q in quantities))
        for op in ops:
            self.assertEqual(op.visit.notes, syringe_note(op.visit.syringes))
            self.assertNotIn('SYNTHETIC', op.visit.notes)
            self.assertNotIn('من ', op.visit.notes)  # multiples of 30 never give a fractional range
        self.assertEqual(sum(quantities), 200 * 90)
        self.assertLessEqual(max(quantities), 150)

    def test_every_visit_has_at_least_the_minimum(self):
        s = make_settings(100, syringes=100 * 30)  # exactly the minimum everywhere
        ops = generate(s, sample_people(100))
        self.assertEqual({o.visit.syringes for o in ops}, {30})
        s = make_settings(100, syringes=100 * 150)  # exactly the maximum everywhere
        self.assertEqual({o.visit.syringes for o in generate(s, sample_people(100))}, {150})

    def test_total_outside_min_max_range_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'يجب أن يكون بين'):
            generate(make_settings(10, syringes=10 * 30 - 30), sample_people(10))
        with self.assertRaisesRegex(ValueError, 'يجب أن يكون بين'):
            generate(make_settings(10, syringes=10 * 150 + 30), sample_people(10))

    def test_total_must_be_multiple_of_thirty(self):
        for bad in (100, 205, 10020 - 10):
            with self.assertRaisesRegex(ValueError, 'مضاعفات'):
                generate(make_settings(10, syringes=bad), sample_people(10))

    def test_custom_min_max(self):
        s = make_settings(50, syringes=50 * 90, minimum_syringes_per_visit=60, maximum_syringes_per_visit=120)
        ops = generate(s, sample_people(50))
        self.assertTrue(validate(ops, s).passed)
        self.assertTrue(all(60 <= o.visit.syringes <= 120 for o in ops))
        with self.assertRaisesRegex(ValueError, 'مضاعفات'):
            generate(make_settings(10, minimum_syringes_per_visit=45), sample_people(10))

    def test_followup_visits_also_get_notes(self):
        s = make_settings(30, start=date(2026, 10, 1), end=date(2026, 10, 31), followup_percent=100,
                          syringes=60 * 90, maximum_syringes_per_visit=150)
        ops = generate(s, sample_people(30))
        self.assertTrue(validate(ops, s).passed)
        self.assertTrue(all(o.visit.notes == syringe_note(o.visit.syringes) for o in ops))


class ScheduleTests(unittest.TestCase):
    def test_outreach_and_area_follow_the_visit_date(self):
        s = make_settings(60)
        ops = generate(s, sample_people(60))
        expected = {d: (n, a) for d, n, a in s.schedule}
        for op in ops:
            self.assertEqual((op.visit.outreach_name, op.visit.area), expected[op.visit.visit_date.isoformat()])
            self.assertEqual(op.visit.actor, ACTORS[op.visit.outreach_name])
        self.assertEqual({o.visit.outreach_name for o in ops}, set(OUTREACH_NAMES[:4]))

    def test_user_example(self):
        s = make_settings(8, schedule=(('2026-11-01', 'احمد عبد الناصر', 'حدائق الاهرام'),
                                      ('2026-11-02', 'سمر', 'الدقي البحوث'),
                                      ('2026-11-03', 'مصطفي', 'هرم كراته'),
                                      ('2026-11-04', 'هند', 'الدقي سليمان جوهر')))
        ops = generate(s, sample_people(8))
        first = next(o for o in ops if o.visit.visit_date == date(2026, 11, 1)).visit
        self.assertEqual((first.outreach_name, first.area), ('احمد عبد الناصر', 'حدائق الاهرام'))
        self.assertEqual({o.visit.outreach_name for o in ops if o.visit.visit_date == date(2026, 11, 4)}, {'هند'})

    def test_incomplete_or_invalid_schedule_is_rejected(self):
        people = sample_people(10)
        good = schedule_for(date(2026, 11, 1), date(2026, 11, 4))
        with self.assertRaisesRegex(ValueError, 'ناقص'):
            generate(make_settings(10, schedule=good[:3]), people)
        with self.assertRaisesRegex(ValueError, 'غير معتمد'):
            generate(make_settings(10, schedule=(('2026-11-01', 'مندوب تجربة 1', 'س'),) + good[1:]), people)
        with self.assertRaisesRegex(ValueError, 'فارغة'):
            generate(make_settings(10, schedule=(('2026-11-01', 'سمر', '  '),) + good[1:]), people)

    def test_no_leftover_placeholder_text_anywhere(self):
        s = make_settings(50)
        ops = generate(s, sample_people(50))
        blob = dump_operations(ops) + csv_bytes(ops).decode('utf-8-sig')
        self.assertNotIn('منطقة اختبار', blob)
        self.assertNotIn('مندوب تجربة', blob)
        self.assertNotIn('Synthetic Tester', blob)


class GeneratorCoreTests(unittest.TestCase):
    def test_totals_and_exact_beneficiaries(self):
        s = make_settings(200, syphilis=5, psychosocial=2, hiv_negative=190)
        ops = generate(s, sample_people(200))
        r = validate(ops, s)
        self.assertTrue(r.passed, r.errors)
        self.assertEqual(len(ops), 200)
        self.assertEqual((r.metrics['syringes'], r.metrics['condoms']), (s.syringes, s.condoms))
        self.assertGreater(r.metrics['lubricants'], 0)  # derived: 2x the condoms of those who take lubricant
        self.assertEqual((r.metrics['hiv_negative'], r.metrics['syphilis'], r.metrics['psychosocial']), (190, 5, 2))

    def test_codes_come_from_the_roster_and_are_unique(self):
        people = sample_people(80)
        ops = generate(make_settings(80), people)
        self.assertEqual({o.code for o in ops}, {p.code for p in people})
        self.assertEqual(len({o.code for o in ops if o.kind == 'NEW'}), 80)
        for person in people:
            visit = next(o.visit for o in ops if o.code == person.code)
            self.assertEqual(visit.birth_date, person.birth_date)

    def test_dates_cover_every_day_in_order(self):
        s = make_settings(50, start=date(2026, 10, 1), end=date(2026, 10, 31))
        ops = generate(s, sample_people(50))
        dates = [o.visit.visit_date for o in ops]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual((dates[0], dates[-1]), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual({d.day for d in dates}, set(range(1, 32)))

    def test_ages_stay_in_range(self):
        ops = generate(make_settings(60, followup_percent=0), sample_people(60))
        self.assertTrue(all(18 <= age_on(o.visit.birth_date, o.visit.visit_date) <= 50 for o in ops))

    def test_followups_same_person_and_later(self):
        s = make_settings(40, start=date(2026, 10, 1), end=date(2026, 10, 31), followup_percent=50,
                          syringes=60 * 90, condoms=600, hiv_negative=60,
                          syphilis=5, psychosocial=2, maximum_syringes_per_visit=150)
        ops = generate(s, sample_people(40))
        r = validate(ops, s)
        self.assertTrue(r.passed, r.errors)
        self.assertEqual((len(ops), r.metrics['unique_codes'], r.metrics['followup_visits']), (60, 40, 20))

    def test_female_count_exact(self):
        s = make_settings(30, female_beneficiaries=11)
        ops = generate(s, sample_people(30))
        self.assertTrue(validate(ops, s).passed)
        self.assertEqual(sum(o.visit.gender == 'أنثى' for o in ops if o.kind == 'NEW'), 11)

    def test_gender_comes_from_the_sheet_when_present(self):
        people = [replace(p, gender='أنثى' if i % 3 == 0 else 'ذكر') for i, p in enumerate(sample_people(30))]
        females = sum(p.gender == 'أنثى' for p in people)
        s = make_settings(30, female_beneficiaries=females)
        ops = generate(s, people)
        self.assertTrue(validate(ops, s).passed)
        by_code = {p.code: p.gender for p in people}
        self.assertTrue(all(o.visit.gender == by_code[o.code] for o in ops))
        with self.assertRaisesRegex(ValueError, 'النوع'):
            generate(make_settings(30, female_beneficiaries=females + 1), people)

    def test_reproducible_with_same_seed_and_different_with_another(self):
        s, people = make_settings(40), sample_people(40)
        self.assertEqual(dump_operations(generate(s, people)), dump_operations(generate(s, people)))
        self.assertNotEqual(dump_operations(generate(s, people)),
                            dump_operations(generate(replace(s, seed=s.seed + 1), people)))

    def test_excluded_codes_stop_generation(self):
        people = sample_people(10)
        with self.assertRaisesRegex(ValueError, 'الاستبعاد'):
            generate(make_settings(10), people, [people[3].code])

    def test_roster_size_must_match(self):
        with self.assertRaises(ValueError):
            generate(make_settings(10), sample_people(9))

    def test_impossible_totals_rejected(self):
        with self.assertRaises(ValueError):
            generate(make_settings(10, syringes=9990), sample_people(10))
        with self.assertRaisesRegex(ValueError, 'الواقيات'):
            generate(make_settings(10, condoms=10 * 100 + 1), sample_people(10))

    def test_distribution_exact(self):
        rng = random.Random(7)
        for n, cap, total in [(1, 90, 50), (10, 4, 39), (3, 0, 0), (50, 100, 3000)]:
            values = distribute_exact(total, n, cap, rng)
            self.assertEqual(sum(values), total)
            self.assertTrue(all(0 <= x <= cap for x in values))


class ValidationTamperingTests(unittest.TestCase):
    def setUp(self):
        self.s = make_settings(20)
        self.ops = generate(self.s, sample_people(20))

    def _tamper(self, index, **changes):
        ops = list(self.ops)
        ops[index] = replace(ops[index], visit=replace(ops[index].visit, **changes))
        return validate(ops, self.s)

    def test_wrong_note_rejected(self):
        self.assertFalse(self._tamper(0, notes='ملاحظة غلط').passed)

    def test_syringes_not_multiple_of_thirty_rejected(self):
        self.assertFalse(self._tamper(0, syringes=self.ops[0].visit.syringes + 10).passed)

    def test_syringes_outside_min_max_rejected(self):
        self.assertFalse(self._tamper(0, syringes=180).passed)
        self.assertFalse(self._tamper(0, syringes=0).passed)

    def test_outreach_not_matching_schedule_rejected(self):
        visit = self.ops[0].visit
        other = next(n for n in OUTREACH_NAMES if n != visit.outreach_name)
        self.assertFalse(self._tamper(0, outreach_name=other, actor=ACTORS[other]).passed)
        self.assertFalse(self._tamper(0, area='منطقة اخرى').passed)

    def test_placeholder_outreach_rejected(self):
        self.assertFalse(self._tamper(0, outreach_name='مندوب تجربة 1', actor='x').passed)

    def test_duplicate_new_rejected(self):
        ops = list(self.ops)
        ops[1] = replace(ops[1], visit=ops[0].visit)
        self.assertFalse(validate(ops).passed)

    def test_invalid_test_result_rejected(self):
        self.assertFalse(self._tamper(0, rapid_result='لم يتم', confirm_result='إيجابي').passed)


class MappingAndFilesTests(unittest.TestCase):
    def test_idus_mapping_and_notes_column(self):
        s = make_settings(20, syringes=20 * 90)
        ops = generate(s, sample_people(20))
        for op in ops:
            cells = base_cells(op.visit, 1)
            self.assertEqual(cells[15], op.code)
            self.assertEqual(cells[3], op.visit.outreach_name)
            self.assertEqual(cells[5], op.visit.area)
            self.assertEqual(cells[55], op.visit.notes)

    def test_json_roundtrip_with_seed_and_csv(self):
        s = make_settings(10)
        ops = generate(s, sample_people(10))
        raw = dump_operations(ops, seed=123)
        self.assertIn('"seed": 123', raw)
        self.assertEqual(dump_operations(load_operations(raw)), dump_operations(ops))
        csv = csv_bytes(ops).decode('utf-8-sig')
        self.assertIn('G_day,H_month,I_year', csv)
        self.assertEqual(visit_record(ops[0])['meeting_place'], 'مقر الجمعية')


if __name__ == '__main__':
    unittest.main()
