"""Derive the beneficiary code from the four-part name, birth date and governorate.

Code = DD MM YY + governorate + first letter of each of the first three names
       + last two letters of the fourth name.
"""
from __future__ import annotations

import re
import unicodedata

from .reference_core import BIRTH_GOVERNORATES

ALPHABET = tuple('ابجدهوزحطيكلمنسعفصقرشتثخذضظغ')
_LETTER_MAP = str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ة': 'ه', 'ى': 'ي',
                             'ؤ': 'و', 'ئ': 'ي', 'ک': 'ك', 'ی': 'ي'})
_MARKS = re.compile('[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]')
_GOV_ALIASES = {'القاهره': 'ق', 'الجيزه': 'ز', 'الاسكندريه': 'ا', 'الإسكندرية': 'ا',
                'الاسكندرية': 'ا', 'القليوبيه': 'ل', 'القليوبية': 'ل', 'القاهرة': 'ق', 'الجيزة': 'ز'}
_COMPOUND_PREFIXES = ('عبد',)


def clean_text(text: str) -> str:
    text = unicodedata.normalize('NFC', str(text or ''))
    text = _MARKS.sub('', text)
    return re.sub(r'\s+', ' ', text).strip()


def split_name(name: str) -> list[str]:
    """Split into given names; 'عبد' is joined to the name that follows it."""
    tokens = clean_text(name).split(' ')
    tokens = [t for t in tokens if t]
    merged, i = [], 0
    while i < len(tokens):
        if tokens[i] in _COMPOUND_PREFIXES and i + 1 < len(tokens):
            merged.append(f'{tokens[i]} {tokens[i + 1]}')
            i += 2
        else:
            merged.append(tokens[i])
            i += 1
    return merged


def to_letter(char: str) -> str:
    letter = char.translate(_LETTER_MAP)
    if letter not in ALPHABET:
        raise ValueError(f'حرف غير مدعوم في الكود: «{char}»')
    return letter


def governorate_code(value) -> str:
    text = clean_text(value)
    if not text:
        raise ValueError('كود محافظة الميلاد فارغ')
    if len(text) == 1:
        return to_letter(text)
    if text in _GOV_ALIASES:
        return _GOV_ALIASES[text]
    for name, code in BIRTH_GOVERNORATES.items():
        if code and text == name:
            return code
    raise ValueError(f'محافظة غير معروفة: «{text}» (اكتب حرف الكود أو اسم المحافظة)')


def _letters(token: str) -> list[str]:
    """Letters of one name. A stand-alone hamza (ء, as in ضياء / بهاء) is not one of the 28 letters, so it is skipped."""
    return [c for c in token.replace(' ', '') if c != 'ء']


def name_letters(name: str) -> tuple[tuple[str, str, str], tuple[str, str]]:
    parts = split_name(name)
    if len(parts) != 4:
        raise ValueError(f'الاسم يجب أن يكون رباعيًا (وجدت {len(parts)} أجزاء)')
    first3 = tuple(to_letter(_letters(p)[0]) for p in parts[:3] if _letters(p))
    if len(first3) != 3:
        raise ValueError('اسم بلا حروف صالحة')
    tail = _letters(parts[3])
    if len(tail) < 2:
        raise ValueError('الاسم الرابع أقل من حرفين')
    last2 = (to_letter(tail[-2]), to_letter(tail[-1]))
    return first3, last2
