"""Pure, testable business rules for the Befrienders IDUs pilot.
No Google credentials and no real beneficiary information are embedded here.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
import re
import unicodedata
import uuid

YES, NO = 'نعم', 'لا'
SHEET_FIRST_ROW = 5
FOLLOWUP_STARTS = [56, 85, 114, 143, 172]  # 0-based: BE, CH, DK, EN, FQ
REFERRAL_OPTIONS = [
    'لا يوجد', 'فحص الزهري', 'دعم نفسي', 'خدمات طبية / جراحية',
    'خدمات قانونية', 'خدمات الحد من الضرر / OST', 'فحص التهاب كبدي B',
    'فحص التهاب كبدي C', 'خدمات الوقاية قبل التعرض', 'أخرى',
]
BIRTH_GOVERNORATES = {'القاهرة': 'ق', 'الجيزة': 'ز', 'الإسكندرية': 'ا', 'القليوبية': 'ل', 'أخرى (حدد الرمز)': ''}

@dataclass(frozen=True)
class Visit:
    visit_date: date
    birth_date: date
    birth_governorate_code: str
    first3: tuple[str, str, str]
    last2: tuple[str, str]
    outreach_name: str
    outreach_governorate: str
    area: str
    meeting_place: str
    gender: str
    condoms: int = 0
    lubricants: int = 0
    syringes: int = 0
    syphilis: bool = False
    psychosocial: bool = False
    ost: bool = False
    referral: str = 'لا يوجد'
    rapid_result: str = 'سلبي'  # سلبي, إيجابي, لم يتم
    confirm_result: str = ''  # سلبي, إيجابي, معلّق, لم يُجرَ
    secondary_syringes: int = 0
    secondary_lubricants: int = 0
    secondary_condoms: int = 0
    secondary_target: str = ''
    notes: str = ''
    actor: str = ''
    syphilis_result: str = ''
    session_type: str = 'فردية'
    previous_hiv_test: str = 'غير محدد'

def components(visit: Visit) -> list[str]:
    tokens = [f'{visit.birth_date.day:02d}', f'{visit.birth_date.month:02d}',
              f'{visit.birth_date.year % 100:02d}', visit.birth_governorate_code,
              *visit.first3, *visit.last2]
    if len(tokens) != 9 or any(len(str(token).strip()) != 1 for token in tokens[3:]):
        raise ValueError('رمز المحافظة والأحرف الخمسة يجب أن يكون كل منها حرفًا واحدًا.')
    return [str(t).strip() for t in tokens]

def composite_code(visit: Visit) -> str:
    return ' '.join(components(visit))

def normalize_code(value: str) -> str:
    text = unicodedata.normalize('NFC', str(value or ''))
    text = text.replace('\u0640', '')  # Tatweel is not identity content
    return re.sub(r'\s+', ' ', text).strip()

def age_on(birth_date: date, at: date) -> int:
    if birth_date > at:
        raise ValueError('تاريخ الميلاد لا يمكن أن يكون بعد تاريخ الزيارة.')
    return at.year - birth_date.year - ((at.month, at.day) < (birth_date.month, birth_date.day))

def age_group(age: int) -> str:
    if age < 15: return 'أقل من 15'
    if age <= 19: return '15 - 19'
    if age <= 24: return '20 - 24'
    if age <= 29: return '25 - 29'
    if age <= 34: return '30 - 34'
    if age <= 39: return '35 - 39'
    if age <= 44: return '40 - 44'
    if age <= 49: return '45 - 49'
    return '50 او اكثر'

def normalized_result(value: str) -> str:
    if value not in ('سلبي', 'إيجابي', 'لم يتم'):
        raise ValueError('نتيجة التحليل السريع غير صالحة.')
    return value

def treatment_linked(visit: Visit) -> bool:
    return visit.rapid_result == 'إيجابي' and visit.confirm_result == 'إيجابي'

def testing_fields(visit: Visit) -> dict[str,str]:
    normalized_result(visit.rapid_result)
    if visit.rapid_result != 'إيجابي' and visit.confirm_result:
        raise ValueError('لا تُدخل نتيجة تأكيدية إلا إذا كان التحليل السريع إيجابيًا.')
    if visit.rapid_result == 'إيجابي' and visit.confirm_result not in ('سلبي','إيجابي','معلّق','لم يُجرَ'):
        raise ValueError('حدد حالة الفحص التأكيدي.')
    has_rapid = visit.rapid_result != 'لم يتم'
    return {
        'rapid_needed': YES if has_rapid else NO,
        'rapid_provided': YES if has_rapid else NO,
        'rapid_result': visit.rapid_result if has_rapid else '',
        'confirm_referred': YES if visit.rapid_result=='إيجابي' and visit.confirm_result!='لم يُجرَ' else NO,
        'confirm_result': visit.confirm_result if visit.confirm_result in ('سلبي','إيجابي') else '',
        'linked': YES if treatment_linked(visit) else NO,
    }

def quantity_fields(qty: int) -> tuple[str, int | str, str, int | str]:
    if isinstance(qty, bool) or not isinstance(qty, int) or qty < 0:
        raise ValueError('الكميات يجب أن تكون أعدادًا صحيحة غير سالبة.')
    return (YES, qty, YES, qty) if qty > 0 else (NO, '', NO, '')

def safe_text(text: str) -> str:
    """Treat user strings as data, never formulas when written to Sheets with RAW."""
    return str(text or '').strip()

def sheets_date(d: date) -> float:
    return float((d - date(1899,12,30)).days)

def base_cells(v:Visit, serial:int) -> dict[int,object]:
    a=age_on(v.birth_date,v.visit_date)
    if a < 15 or a > 100:
        raise ValueError('السن خارج النطاق المحدد للتجربة (15 إلى 100).')
    t=testing_fields(v)
    initial=[
        serial,'بي فريندرز',sheets_date(v.visit_date),safe_text(v.outreach_name),
        safe_text(v.outreach_governorate),safe_text(v.area),*components(v),composite_code(v),
        safe_text(v.meeting_place),age_group(a),safe_text(v.gender),NO,'',YES,YES,YES,
    ]
    if len(initial)!=24: raise AssertionError('Unexpected initial schema length')
    row={i:initial[i] for i in range(24)}  # A:X
    def put(start,q):
        for k,val in enumerate(quantity_fields(q)):row[start+k]=val
    put(24,v.condoms)       # Y:AB
    put(28,v.lubricants)    # AC:AF
    row.update({32:YES if v.syphilis else NO,33:YES if v.syphilis else NO,
                34:YES if v.psychosocial else NO,35:YES if v.psychosocial else NO})
    put(36,v.syringes)      # AK:AN
    row.update({40:YES if v.ost else NO,41:YES if v.ost else NO})
    has_ref=v.referral!='لا يوجد'
    row.update({42:YES if has_ref else NO,43:YES if has_ref else NO,
                44:v.referral if has_ref else '',45:YES,
                46:t['rapid_provided'],47:t['rapid_result'],48:t['confirm_referred'],
                49:t['confirm_result'],50:t['linked'],
                51:v.secondary_syringes or '',52:v.secondary_lubricants or '',
                53:v.secondary_condoms or '',54:v.secondary_target or '',55:v.notes or ''})
    return row

def followup_cells(v:Visit, start_col:int)->dict[int,object]:
    if start_col not in FOLLOWUP_STARTS:raise ValueError('مجموعة متابعة غير معروفة')
    t=testing_fields(v)
    def seq(q:int):return list(quantity_fields(q))
    has_ref=v.referral!='لا يوجد'
    arr=[sheets_date(v.visit_date),YES,YES,
         *seq(v.condoms),*seq(v.lubricants),
         YES if v.syphilis else NO,YES if v.syphilis else NO,
         YES if v.psychosocial else NO,YES if v.psychosocial else NO,
         *seq(v.syringes),
         t['rapid_needed'],t['rapid_provided'],t['rapid_result'],
         YES if v.ost else NO,YES if v.ost else NO,
         YES if has_ref else NO,YES if has_ref else NO,
         v.referral if has_ref else '',YES,v.notes or '']
    assert len(arr)==29, f'Incorrect followup width {len(arr)}'
    return {start_col+i:value for i,value in enumerate(arr)}

def total_formulas(row_number:int) -> dict[int,str]:
    n=row_number
    # Include all 5 follow-ups. The original Excel file has inconsistent sum formulas.
    return {201:f'=SUM(AB{n},BK{n},CN{n},DQ{n},ET{n},FW{n})',
            202:f'=SUM(AF{n},BO{n},CR{n},DU{n},EX{n},GA{n})',
            203:f'=SUM(AN{n},BW{n},CZ{n},EC{n},FF{n},GI{n})'}

def make_audit(v: Visit, row:int, is_followup:bool)->list[object]:
    t=testing_fields(v)
    return [str(uuid.uuid4()),datetime.now().astimezone().isoformat(timespec='seconds'),
            v.actor or v.outreach_name,row,'متابعة' if is_followup else 'أول مرة',
            composite_code(v),v.visit_date.isoformat(),t['rapid_result'],
            v.confirm_result if v.rapid_result=='إيجابي' else '',t['linked'],
            v.syringes,v.condoms,v.lubricants,YES if v.syphilis else NO,v.referral,YES,v.syphilis_result if v.syphilis else '',v.session_type,v.previous_hiv_test]
