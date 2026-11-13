"""Business rules shared by the generator and the validator."""
from __future__ import annotations

OUTREACH_NAMES = ['احمد عبد الناصر', 'احمد طارق', 'مصطفي', 'سمر', 'هند']
# English names written to the `actor` field (same convention as the cleaned archive).
ACTORS = {
    'احمد عبد الناصر': 'abdelnasir',
    'احمد طارق': 'tarek',
    'مصطفي': 'Mostafa',
    'سمر': 'Samar',
    'هند': 'Hend',
}
SYRINGE_STEP = 30          # per-visit syringes are multiples of 30 (so quantity / 30 is never fractional)
MIN_AGE = 18               # beneficiaries must be 18-50 on every visit date
MAX_AGE = 50
SYRINGE_MIN_DEFAULT = 30
SYRINGE_MAX_DEFAULT = 150
SYRINGE_DOSES_PER_DAY_DIVISOR = 30  # Quantity for one approximate daily injection over a month


def _arabic_number(value: int) -> str:
    """Render count in Arabic-Indic digits in the narrative notes only."""
    return str(value).translate(str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩'))


def syringe_note(quantity: int) -> str:
    """Generate a monthly-supply note for every positive syringe quantity (no >90 threshold).

    The regular allocation uses multiples of 30, representing approximate daily use.
    Nonmultiples retain the earlier approximate range explanation.
    """
    if quantity <= 0:
        return ''
    low, remainder = divmod(quantity, SYRINGE_DOSES_PER_DAY_DIVISOR)
    if remainder:
        frequency = f'من {_arabic_number(low)} إلى {_arabic_number(low + 1)} مرات'
        return f'المستفيد بيضرب {frequency} في اليوم واستلم كمية شهر'
    if low == 1:
        frequency = 'مرة واحدة'
    elif low == 2:
        frequency = 'مرتين'
    else:
        frequency = f'{_arabic_number(low)} مرات'
    return f'المستفيد بيضرب تقريبا {frequency} في اليوم واستلم كمية شهر'


def condom_note(condoms: int) -> str:
    """Two condoms per expected monthly sexual act, for positive quantities only."""
    acts = condoms // 2
    if acts <= 0:
        return ''
    if acts == 1:
        frequency = 'علاقة جنسية واحدة'
    elif acts == 2:
        frequency = 'علاقتين جنسيتين'
    elif acts <= 10:
        frequency = f'{_arabic_number(acts)} علاقات جنسية'
    else:
        frequency = f'{_arabic_number(acts)} علاقة جنسية'
    return f'المستفيد يمارس {frequency} في الشهر واستلم كمية شهر'


def visit_note(syringes: int, condoms: int) -> str:
    """Generate the canonical notes for generator and validation alike."""
    return ' - '.join(part for part in (syringe_note(syringes), condom_note(condoms)) if part)
