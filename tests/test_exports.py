import json
import unittest
from datetime import date

from befrienders_tester.exporter import excel_bytes
from befrienders_tester.generator import generate
from befrienders_tester.rules import syringe_note
from befrienders_tester.training_export import training_excel_bytes
from befrienders_tester.validation import validate
from tests.helpers import make_settings, sample_people, sheet_values


class TrainingExportTests(unittest.TestCase):
    def setUp(self):
        self.s = make_settings(30, syringes=30 * 90)
        self.ops = generate(self.s, sample_people(30))
        self.excel = training_excel_bytes(self.ops, seed=4242)

    def test_records_carry_no_synthetic_or_trial_labels(self):
        training = sheet_values(self.excel, 1)
        for row, op in enumerate(self.ops, start=2):
            payload = json.loads(training[f'E{row}'])
            self.assertEqual(payload['notes'], syringe_note(op.visit.syringes))
            self.assertEqual(payload['outreach_name'], op.visit.outreach_name)
            self.assertEqual(payload['area'], op.visit.area)
            self.assertNotIn('SYNTHETIC', training[f'E{row}'])
            self.assertNotIn('مندوب تجربة', training[f'E{row}'])
            self.assertNotIn('منطقة اختبار', training[f'E{row}'])
            self.assertNotIn('Synthetic', training[f'E{row}'])
            self.assertNotEqual(payload['actor'], '')

    def test_idus_sheet_has_unique_codes_and_clean_notes(self):
        idus = sheet_values(self.excel, 0)
        codes = [idus[f'P{r}'] for r in range(5, 5 + len(self.ops))]
        self.assertEqual(len(codes), len(set(codes)))
        for r, op in enumerate(self.ops, start=5):
            self.assertEqual(idus[f'D{r}'], op.visit.outreach_name)
            self.assertEqual(idus[f'F{r}'], op.visit.area)
            self.assertNotIn('SYNTHETIC', str(idus.get(f'BD{r}', '')))

    def test_file_level_marker_and_seed_in_test_info(self):
        info = sheet_values(self.excel, 2)
        self.assertEqual(info['B1'], 'SYNTHETIC_ONLY')
        self.assertEqual(info['B4'], 4242)

    def test_followups_inside_30_days_are_refused(self):
        s = make_settings(10, start=date(2026, 10, 1), end=date(2026, 10, 20), followup_percent=100,
                          syringes=20 * 60, condoms=100, hiv_negative=20,
                          syphilis=1, psychosocial=1)
        ops = generate(s, sample_people(10))
        with self.assertRaises(ValueError):
            training_excel_bytes(ops)


class ReviewWorkbookTests(unittest.TestCase):
    def test_review_excel_builds(self):
        s = make_settings(15)
        ops = generate(s, sample_people(15))
        data = excel_bytes(ops, validate(ops, s))
        self.assertTrue(len(data) > 1000)


if __name__ == '__main__':
    unittest.main()
