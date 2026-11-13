"""Condoms / lubricants / syringes: steps, 'lubricant = 2 x condoms', optional number of people."""
import unittest
from collections import Counter
from dataclasses import replace

from befrienders_tester.generator import generate
from befrienders_tester.validation import validate
from tests.helpers import make_settings, sample_people


def scenario(n=55, **kw):
    base = dict(syringes=4500, condoms=480, syphilis=3, psychosocial=2, hiv_negative=n,
                syringe_people=n, condom_people=30, lubricant_people=20)
    base.update(kw)
    return make_settings(n, **base)


class StepsTests(unittest.TestCase):
    def test_condoms_are_even_and_lubricants_follow(self):
        seen = set()
        for seed in range(1, 6):
            s = make_settings(80, condoms=80 * 10, seed=seed)
            ops = generate(s, sample_people(80))
            self.assertTrue(validate(ops, s).passed)
            for op in ops:
                self.assertEqual((op.visit.condoms % 2, op.visit.lubricants % 2), (0, 0))
                self.assertEqual(op.visit.lubricants % 4, 0)       # double of an even number
                seen.add(op.visit.condoms)
        self.assertTrue({2, 4, 6, 8, 12} & seen)                   # real even values, not only multiples of 5

    def test_user_example_30_condoms_means_60_lubricant(self):
        s = make_settings(40, condoms=40 * 30, condom_people=40, lubricant_people=40, maximum_condoms_per_visit=30)
        ops = generate(s, sample_people(40))
        self.assertTrue(validate(ops, s).passed)
        self.assertTrue(all(o.visit.condoms == 30 and o.visit.lubricants == 60 for o in ops))

    def test_odd_totals_are_rejected(self):
        for bad in (481, 7):
            with self.assertRaisesRegex(ValueError, 'مضاعفات 2'):
                generate(scenario(condoms=bad), sample_people(55))

    def test_lubricant_is_double_the_condoms_and_never_without_them(self):
        s = make_settings(120, condoms=120 * 10)
        ops = generate(s, sample_people(120))
        self.assertTrue(validate(ops, s).passed)
        with_lub = [o.visit for o in ops if o.visit.lubricants]
        self.assertTrue(with_lub)
        for v in with_lub:
            self.assertGreater(v.condoms, 0)
            self.assertEqual(v.lubricants, 2 * v.condoms)
        # not everyone takes condoms and not every condom taker takes lubricant
        self.assertTrue(any(o.visit.condoms == 0 for o in ops))
        self.assertTrue(any(o.visit.condoms > 0 and o.visit.lubricants == 0 for o in ops))

    def test_lubricant_total_is_derived_and_input_is_ignored(self):
        s = make_settings(60, condoms=600, lubricants=12345)
        ops = generate(s, sample_people(60))
        self.assertTrue(validate(ops, s).passed)
        self.assertEqual(sum(o.visit.lubricants for o in ops),
                         2 * sum(o.visit.condoms for o in ops if o.visit.lubricants))


class PeopleCountTests(unittest.TestCase):
    def test_user_example(self):
        """55 people: syringes 4500 for 55, condoms 480 for 30, lubricant for 20."""
        s = scenario()
        ops = generate(s, sample_people(55))
        r = validate(ops, s)
        self.assertTrue(r.passed, r.errors)
        self.assertEqual((r.metrics['syringes'], r.metrics['condoms']), (4500, 480))
        self.assertEqual((r.metrics['syringe_recipients'], r.metrics['condom_recipients'],
                          r.metrics['lubricant_recipients']), (55, 30, 20))
        takers = [o.visit for o in ops if o.visit.condoms]
        self.assertEqual(len(takers), 30)
        self.assertTrue(all(v.condoms >= 2 and v.condoms % 2 == 0 for v in takers))
        lub = [o.visit for o in ops if o.visit.lubricants]
        self.assertEqual(len(lub), 20)
        self.assertEqual(r.metrics['lubricants'], 2 * sum(v.condoms for v in lub))
        self.assertTrue(all(v.condoms > 0 for v in lub))

    def test_syringes_for_fewer_people_than_visits(self):
        s = scenario(syringes=40 * 90, syringe_people=40, condom_people=None, lubricant_people=None, condoms=300)
        ops = generate(s, sample_people(55))
        r = validate(ops, s)
        self.assertTrue(r.passed, r.errors)
        self.assertEqual(sum(o.visit.syringes > 0 for o in ops), 40)
        self.assertTrue(all(o.visit.syringes in (0, 30, 60, 90, 120, 150) for o in ops))
        for o in ops:
            self.assertEqual(o.visit.notes == '', o.visit.syringes <= 90)

    def test_no_counts_means_automatic_distribution(self):
        s = make_settings(55, syringes=55 * 60, condoms=550)
        ops = generate(s, sample_people(55))
        self.assertTrue(validate(ops, s).passed)
        self.assertEqual(sum(o.visit.syringes > 0 for o in ops), 55)

    def test_same_seed_same_result(self):
        a = [(o.code, o.visit.syringes, o.visit.condoms, o.visit.lubricants) for o in generate(scenario(), sample_people(55))]
        b = [(o.code, o.visit.syringes, o.visit.condoms, o.visit.lubricants) for o in generate(scenario(), sample_people(55))]
        self.assertEqual(a, b)

    def test_invalid_counts_are_rejected_with_a_clear_message(self):
        people = sample_people(55)
        with self.assertRaisesRegex(ValueError, 'أكبر من عدد من يأخذ الواقي'):
            generate(scenario(lubricant_people=31), people)
        with self.assertRaisesRegex(ValueError, 'حدد عدد أشخاص الواقي'):
            generate(scenario(condom_people=None, lubricant_people=10), people)
        with self.assertRaisesRegex(ValueError, 'عدد أشخاص'):
            generate(scenario(condom_people=56), people)
        with self.assertRaisesRegex(ValueError, 'الواقيات'):
            generate(scenario(condoms=30 * 2 - 2), people)            # below 2 per person
        with self.assertRaisesRegex(ValueError, 'الواقيات'):
            generate(scenario(condoms=30 * 100 + 2), people)          # above the cap
        with self.assertRaisesRegex(ValueError, 'السرنجات'):
            generate(scenario(syringes=55 * 150 + 30), people)
        with self.assertRaisesRegex(ValueError, 'مضاعفات'):
            generate(scenario(condoms=481), people)


class MaximumPerVisitTests(unittest.TestCase):
    """Every item keeps its per-visit maximum, including the lubricant (= 2 x condoms)."""

    def _check_caps(self, ops, s):
        for op in ops:
            v = op.visit
            self.assertLessEqual(v.syringes, s.maximum_syringes_per_visit)
            self.assertLessEqual(v.condoms, s.maximum_condoms_per_visit)
            self.assertLessEqual(v.lubricants, s.maximum_lubricants_per_visit)

    def test_defaults_hold_across_many_seeds_and_modes(self):
        people = sample_people(55)
        for seed in range(1, 31):
            for extra in ({}, {'condom_people': 30, 'condoms': 480}, {'condom_people': 30, 'condoms': 480, 'lubricant_people': 20}):
                s = make_settings(55, seed=seed, syringes=55 * 90, syphilis=3, psychosocial=2, **extra)
                ops = generate(s, people)
                r = validate(ops, s)
                self.assertTrue(r.passed, (seed, extra, r.errors[:2]))
                self._check_caps(ops, s)

    def test_tight_lubricant_maximum_limits_the_condoms_of_lubricant_takers(self):
        s = scenario(maximum_lubricants_per_visit=40)
        ops = generate(s, sample_people(55))
        r = validate(ops, s)
        self.assertTrue(r.passed, r.errors)
        self._check_caps(ops, s)
        takers = [o.visit for o in ops if o.visit.lubricants]
        self.assertEqual(len(takers), 20)
        self.assertTrue(all(v.condoms <= 20 and v.lubricants == 2 * v.condoms <= 40 for v in takers))
        self.assertEqual(sum(o.visit.condoms for o in ops), 480)

    def test_automatic_mode_respects_the_lubricant_maximum(self):
        s = make_settings(80, condoms=80 * 15, maximum_lubricants_per_visit=30)
        ops = generate(s, sample_people(80))
        self.assertTrue(validate(ops, s).passed)
        self.assertTrue(all(o.visit.lubricants <= 30 for o in ops))
        self.assertTrue(any(o.visit.lubricants for o in ops))

    def test_maximum_below_four_means_no_lubricant(self):
        s = scenario(maximum_lubricants_per_visit=2, lubricant_people=None)
        ops = generate(s, sample_people(55))
        self.assertTrue(validate(ops, s).passed)
        self.assertEqual(sum(o.visit.lubricants for o in ops), 0)
        with self.assertRaisesRegex(ValueError, 'أقل من 4'):
            generate(scenario(maximum_lubricants_per_visit=2), sample_people(55))

    def test_infeasible_combination_gives_a_clear_message(self):
        # 20 lubricant takers can hold at most 10 condoms each: 20*10 + 10*100 = 1200 < 1300
        with self.assertRaisesRegex(ValueError, 'أقصى إجمالي ممكن'):
            generate(scenario(condoms=1300, maximum_lubricants_per_visit=20), sample_people(55))

    def test_maximum_must_be_even(self):
        with self.assertRaisesRegex(ValueError, 'للمزلقات'):
            generate(scenario(maximum_lubricants_per_visit=41), sample_people(55))


class TamperingTests(unittest.TestCase):
    def setUp(self):
        self.s = scenario()
        self.ops = generate(self.s, sample_people(55))

    def _tamper(self, predicate, **changes):
        ops = list(self.ops)
        i = next(i for i, o in enumerate(ops) if predicate(o.visit))
        ops[i] = replace(ops[i], visit=replace(ops[i].visit, **changes))
        return validate(ops, self.s)

    def test_lubricant_not_double_is_rejected(self):
        self.assertFalse(self._tamper(lambda v: v.lubricants, lubricants=15).passed)

    def test_lubricant_without_condoms_is_rejected(self):
        self.assertFalse(self._tamper(lambda v: v.condoms == 0, lubricants=10).passed)

    def test_odd_condoms_are_rejected(self):
        self.assertFalse(self._tamper(lambda v: v.condoms, condoms=7, lubricants=0).passed)
        self.assertFalse(self._tamper(lambda v: v.condoms, condoms=15, lubricants=30).passed)

    def test_lubricant_above_its_maximum_is_rejected(self):
        # keeps lubricant == 2 x condoms but exceeds the 100 maximum
        r = self._tamper(lambda v: v.lubricants, condoms=60, lubricants=120)
        self.assertFalse(r.passed)
        self.assertTrue(any('الحد الأقصى' in e for e in r.errors))

    def test_wrong_number_of_recipients_is_rejected(self):
        self.assertFalse(self._tamper(lambda v: v.condoms == 0, condoms=4).passed)


if __name__ == '__main__':
    unittest.main()
