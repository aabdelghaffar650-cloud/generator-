"""Read the uploaded roster workbook: full name, birth date, birth governorate.

The workbook is only parsed here; nothing is written back and no file is linked.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .codes import governorate_code, name_letters
from .reference_core import age_on, normalize_code
from .rules import MAX_AGE, MIN_AGE

MAX_ROWS = 10000
_DATE_FORMATS = ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y/%m/%d', '%d.%m.%Y', '%d/%m/%y')
_ARABIC_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


@dataclass(frozen=True)
class Person:
    row: int
    name: str
    birth_date: date
    gov: str
    first3: tuple[str, str, str]
    last2: tuple[str, str]
    gender: str = ''  # optional 4th column: 'ذكر' / 'أنثى', empty when the sheet has no gender column

    @property
    def code(self) -> str:
        return normalize_code(' '.join([f'{self.birth_date.day:02d}', f'{self.birth_date.month:02d}',
                                        f'{self.birth_date.year % 100:02d}', self.gov,
                                        *self.first3, *self.last2]))


def parse_birth_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 1000 < value < 100000:
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = str(value or '').strip().translate(_ARABIC_DIGITS)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'تاريخ ميلاد غير مفهوم: «{value}»')


_GENDERS = {'ذكر': 'ذكر', 'ذكرا': 'ذكر', 'm': 'ذكر', 'male': 'ذكر',
            'أنثى': 'أنثى', 'انثى': 'أنثى', 'انثي': 'أنثى', 'أنثي': 'أنثى', 'f': 'أنثى', 'female': 'أنثى'}


def parse_gender(value) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        return _GENDERS[text.lower()]
    except KeyError:
        raise ValueError(f'النوع غير مفهوم: «{value}» (ذكر / أنثى)')


def read_roster(data: bytes, window_start: date, window_end: date, enforce_age: bool = True):
    """Return (people, errors). Errors carry the Excel row number; nothing is guessed."""
    import openpyxl
    errors: list[str] = []
    try:
        sheet = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True).worksheets[0]
    except Exception as exc:  # corrupted / not an xlsx
        return [], [f'تعذر فتح الملف: {exc}']
    rows = [tuple(r[:4]) + (None,) * (4 - len(r[:4])) for r in sheet.iter_rows(values_only=True)]
    first_row = 1
    if rows:
        try:
            parse_birth_date(rows[0][1])
        except ValueError:
            first_row = 2  # header row
            rows = rows[1:]
    people: list[Person] = []
    seen: dict[str, int] = {}
    for offset, (name, birth, gov, gender) in enumerate(rows):
        row = first_row + offset
        if not any(str(x or '').strip() for x in (name, birth, gov, gender)):
            continue
        try:
            birth_date = parse_birth_date(birth)
            gov_code = governorate_code(gov)
            gender_value = parse_gender(gender)
            first3, last2 = name_letters(name)
            if enforce_age and (age_on(birth_date, window_start) < MIN_AGE or age_on(birth_date, window_end) > MAX_AGE):
                raise ValueError(f'السن خارج {MIN_AGE}–{MAX_AGE} خلال فترة الزيارات')
        except ValueError as exc:
            errors.append(f'صف {row}: {exc}')
            continue
        person = Person(row, str(name).strip(), birth_date, gov_code, first3, last2, gender_value)
        if person.code in seen:
            errors.append(f'صف {row}: الكود «{person.code}» مكرر مع صف {seen[person.code]}')
            continue
        seen[person.code] = row
        people.append(person)
    if any(p.gender for p in people):  # a gender column is in use: every row must carry it
        for person in [p for p in people if not p.gender]:
            errors.append(f'صف {person.row}: النوع فارغ بينما باقي الصفوف فيها نوع')
        people = [p for p in people if p.gender]
    if len(people) + len(errors) > MAX_ROWS:
        errors.append(f'عدد الصفوف يتجاوز {MAX_ROWS}')
    return people, errors
