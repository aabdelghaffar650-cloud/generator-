"""Test fixtures: fictional people, schedules and settings. No real data."""
import io
import random
from datetime import date, timedelta

import openpyxl

from befrienders_tester.codes import name_letters
from befrienders_tester.model import Settings
from befrienders_tester.rules import OUTREACH_NAMES
from befrienders_tester.roster import Person

POOL = ['كريم', 'علي', 'محمد', 'حسن', 'سمير', 'ياسر', 'هاني', 'وليد', 'طارق', 'عمرو', 'خالد', 'ايمن',
        'محمود', 'ابراهيم', 'سعيد', 'فتحي', 'رضا', 'جمال', 'نبيل', 'صلاح', 'عادل', 'ماجد', 'بهاء', 'شريف']
AREAS = ['حدائق الاهرام', 'الدقي البحوث', 'هرم كراته', 'الدقي سليمان جوهر']


def sample_people(n, seed=1):
    rng = random.Random(seed)
    people, seen = [], set()
    while len(people) < n:
        name = ' '.join(rng.choice(POOL) for _ in range(4))
        birth = date(1980, 1, 1) + timedelta(days=rng.randrange(365 * 18))
        gov = rng.choice('زق')
        first3, last2 = name_letters(name)
        person = Person(len(people) + 2, name, birth, gov, first3, last2)
        if person.code not in seen:
            seen.add(person.code)
            people.append(person)
    return people


def schedule_for(start, end):
    days = (end - start).days + 1
    return tuple(((start + timedelta(days=i)).isoformat(), OUTREACH_NAMES[i % 5], AREAS[i % 4])
                 for i in range(days))


def make_settings(n=40, start=date(2026, 11, 1), end=date(2026, 11, 4), **kw):
    base = dict(beneficiaries=n, syringes=n * 60, condoms=n * 10, lubricants=0, hiv_negative=n,
                hiv_positive=0, confirm_positive=0, syphilis=min(5, n), psychosocial=min(2, n),
                followup_percent=0, seed=7, maximum_syringes_per_visit=150,
                visit_start=start.isoformat(), visit_end=end.isoformat(), female_beneficiaries=0,
                schedule=schedule_for(start, end))
    base.update(kw)
    return Settings(**base)


def roster_xlsx(rows, header=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    if header:
        ws.append(['الاسم', 'تاريخ الميلاد', 'المحافظة'])
    for row in rows:
        ws.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def sheet_values(xlsx_bytes, index):
    ws = openpyxl.load_workbook(io.BytesIO(xlsx_bytes)).worksheets[index]
    return {c.coordinate: c.value for row in ws.iter_rows() for c in row if c.value is not None}
