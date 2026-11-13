"""Build a fictional roster workbook (name, birth date, governorate, gender) for testing.

Names are random combinations of common given names, so they do not point to real
people. Codes are unique, and every age stays within 15-50 across the given window.

    python tools/make_sample_roster.py 200 2026-11-01 2026-11-04 sample_roster.xlsx [seed]
    python tools/make_sample_roster.py 55 2026-11-01 2026-11-04 new55.xlsx 5502 --females 7 --exclude old200.xlsx

Ages are always 18-50 with a 2-year safety margin on both sides. `--females N` gives exactly N women;
`--exclude` skips every code and every full name that already appears in an earlier roster file.
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import openpyxl  # noqa: E402
from befrienders_tester.codes import name_letters  # noqa: E402
from befrienders_tester.reference_core import age_on  # noqa: E402
from befrienders_tester.roster import Person, read_roster  # noqa: E402
from befrienders_tester.rules import MAX_AGE, MIN_AGE  # noqa: E402

MALE = ['محمد', 'احمد', 'محمود', 'مصطفي', 'علي', 'حسن', 'حسين', 'ابراهيم', 'اسماعيل', 'يوسف', 'عمر', 'عمرو',
        'خالد', 'طارق', 'ياسر', 'هاني', 'وليد', 'سمير', 'سامح', 'شريف', 'ايمن', 'اشرف', 'رضا', 'سعيد', 'صلاح',
        'عادل', 'ماجد', 'نبيل', 'جمال', 'كريم', 'هشام', 'تامر', 'اسلام', 'رامي', 'حازم', 'ماهر', 'ناصر', 'فتحي',
        'عصام', 'مجدي', 'سيد', 'عبد الله', 'عبد الرحمن', 'عبد العزيز', 'عبد الناصر', 'ربيع', 'حمدي', 'زكريا']
FEMALE = ['منى', 'سارة', 'هبة', 'نهى', 'دعاء', 'رشا', 'ايمان', 'سمر', 'هند', 'مروة', 'فاطمة', 'نورا', 'امل',
          'اسماء', 'ريهام', 'داليا', 'شيماء', 'ياسمين', 'مريم', 'عبير']
FEMALE_SHARE = 0.3


def make_name(rng):
    """First name (male or female) + father, grandfather and great-grandfather (all male, all different)."""
    first = rng.choice(FEMALE) if rng.random() < FEMALE_SHARE else rng.choice(MALE)
    lineage = rng.sample([m for m in MALE if m != first], 3)
    return ' '.join([first, *lineage]), first in FEMALE


def build(n, start, end, seed=2026, females=None, exclude_codes=(), exclude_names=()):
    rng = random.Random(seed)
    earliest = end - timedelta(days=(MAX_AGE - 2) * 365)
    latest = start - timedelta(days=(MIN_AGE + 2) * 365)
    female_slots = set(rng.sample(range(n), females)) if females is not None else None
    rows, seen_codes, seen_names = [], set(exclude_codes), set(exclude_names)
    while len(rows) < n:
        is_female = (len(rows) in female_slots) if female_slots is not None else rng.random() < FEMALE_SHARE
        first = rng.choice(FEMALE) if is_female else rng.choice(MALE)
        lineage = rng.sample([m for m in MALE if m != first], 3)
        name = ' '.join([first, *lineage])
        if name in seen_names:
            continue
        birth = earliest + timedelta(days=rng.randrange((latest - earliest).days))
        if not (MIN_AGE <= age_on(birth, start) and age_on(birth, end) <= MAX_AGE):
            continue
        gov = rng.choice('زق')
        try:
            first3, last2 = name_letters(name)
        except ValueError:
            continue
        person = Person(len(rows) + 2, name, birth, gov, first3, last2)
        if person.code in seen_codes:
            continue
        seen_codes.add(person.code)
        seen_names.add(name)
        rows.append((name, birth, 'الجيزة' if gov == 'ز' else 'القاهرة', 'أنثى' if is_female else 'ذكر'))
    return rows


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('n', type=int)
    ap.add_argument('start', type=date.fromisoformat)
    ap.add_argument('end', type=date.fromisoformat)
    ap.add_argument('out')
    ap.add_argument('seed', type=int, nargs='?', default=2026)
    ap.add_argument('--females', type=int, default=None)
    ap.add_argument('--exclude', action='append', default=[], help='earlier roster workbook(s) to avoid')
    args = ap.parse_args()
    old_codes, old_names = set(), set()
    for path in args.exclude:
        people, _ = read_roster(Path(path).read_bytes(), args.start, args.end, enforce_age=False)
        old_codes |= {p.code for p in people}
        old_names |= {p.name for p in people}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'المستفيدون'
    ws.sheet_view.rightToLeft = True
    ws.append(['الاسم الرباعي', 'تاريخ الميلاد', 'محافظة الميلاد', 'النوع'])
    for name, birth, gov, gender in build(args.n, args.start, args.end, args.seed, args.females, old_codes, old_names):
        ws.append([name, birth, gov, gender])
    for cell in ws['B'][1:]:
        cell.number_format = 'dd/mm/yyyy'
    for col, width in zip('ABCD', (34, 16, 16, 10)):
        ws.column_dimensions[col].width = width
    wb.save(args.out)
    print('saved', args.out, args.n)
