"""Training-Pilot-compatible XLSX export for synthetic operations only.

Based on the header/worksheet layout of user-supplied
Befrienders_TRAINING_APPROVED_IDUs.xlsx (2026-11-08).
Never imports the uploaded workbook's beneficiary records or credentials.
This is an offline file export; it does not connect to the Google Pilot.
"""
from __future__ import annotations

import io
import json
from collections import OrderedDict
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .model import TAG
from .reference_core import FOLLOWUP_STARTS, base_cells, followup_cells, total_formulas

_SCHEMA_PATH = Path(__file__).resolve().parent / 'assets' / 'training_approved_headers.json'
_TRAINING_COLUMNS = ['submission_id', 'kind', 'code', 'date', 'visit_json', 'status', 'worker_id']


def _schema():
    with _SCHEMA_PATH.open(encoding='utf-8') as stream:
        schema = json.load(stream)
    assert schema['sheets'] == ['IDUs', 'TRAINING_RECORDS', 'TEST_INFO']
    assert schema['training_record_headers'] == _TRAINING_COLUMNS
    assert all(len(schema['headers'][str(n)]) == 204 for n in (1, 2, 4))
    return schema


def _payload(v):
    record = asdict(v)
    record['visit_date'] = v.visit_date.isoformat()
    record['birth_date'] = v.birth_date.isoformat()
    # The generator exposes delivered quantities, not separately requested quantities.
    # Explicitly mark them equal; do not fabricate extra demand.
    record['requested_quantities'] = {
        'syringes': int(v.syringes),
        'condoms': int(v.condoms),
        'lubricants': int(v.lubricants),
    }
    record['notes'] = str(record.get('notes') or '').strip()
    return record


def training_excel_bytes(ops, *, worker_id='outreach_1', seed=None):
    """Export exact 3-sheet Training-compatible layout, no copied template records.

    A:GV matches IDUs; TRAINING_RECORDS contains an APPPROVED-shaped test fixture
    for each visit, with complete visit_json for local form rendering.

    Deliberately fail closed on historical follow-ups and follow-ups less than 30
    days after the first visit: Training Pilot's eligibility rules would reject them.
    """
    import xlsxwriter

    worker_id = str(worker_id).strip()
    if not worker_id or len(worker_id) > 64 or any(c in worker_id for c in '\n\r\t'):
        raise ValueError('Training worker_id must be 1–64 characters without newlines.')
    if not ops:
        raise ValueError('لا توجد سجلات لتصديرها.')
    schema = _schema()
    by_code = OrderedDict()
    for op in ops:
        if op.kind == 'NEW':
            if op.code in by_code:
                raise ValueError('يوجد كود NEW مكرر؛ تم رفض التصدير.')
            by_code[op.code] = {'new': op, 'followups': []}
        elif op.kind == 'FOLLOWUP':
            if op.code not in by_code:
                raise ValueError('متابعة ليس لها مستفيد NEW داخل المجموعة.')
            first = by_code[op.code]['new'].visit.visit_date
            if (op.visit.visit_date - first).days < 30:
                raise ValueError('Training Pilot يتطلب مرور 30 يومًا قبل المتابعة؛ صدّر مجموعة الزيارات الأولى فقط حاليًا.')
            by_code[op.code]['followups'].append(op)
        else:
            raise ValueError('متابعات الأكواد التاريخية ليست ضمن تصدير Training المستقل حفاظًا على المرجع.')
    if any(len(v['followups']) > 5 for v in by_code.values()):
        raise ValueError('الحد الأقصى خمسة متابعات لكل مستفيد.')

    result = io.BytesIO()
    workbook = xlsxwriter.Workbook(result, {'in_memory': True})
    workbook.set_properties({'title': 'Befrienders Synthetic Training Test',
                             'comments': TAG})
    section = workbook.add_format({'font_name':'Arial', 'font_size':10, 'bold':True,
                                   'bg_color':'#CFE4F2', 'font_color':'#17344E',
                                   'align':'center','valign':'vcenter','text_wrap':True})
    header = workbook.add_format({'font_name':'Arial', 'font_size':9, 'bold':True,
                                  'bg_color':'#DCEAF2','font_color':'#18364D',
                                  'align':'center','valign':'vcenter','text_wrap':True})
    subheader = workbook.add_format({'font_name':'Arial', 'font_size':9,
                                     'font_color':'#17344E','align':'center'})
    datefmt = workbook.add_format({'num_format':'dd/mm/yyyy'})
    identity = workbook.add_format({'num_format':'@', 'font_name':'Arial'})
    center = workbook.add_format({'align':'center'})
    title = workbook.add_format({'bold':True,'font_color':'white','bg_color':'#9A2D3F'})
    longtext = workbook.add_format({'text_wrap':False})

    # Use EXACT sheet names, column count, group headings and subheadings
    # from the approved sample; the source's data rows are not copied.
    idus = workbook.add_worksheet('IDUs')
    idus.right_to_left()
    idus.freeze_panes(4, 0)
    idus.set_tab_color('#236D8B')
    idus.set_row(0,30)
    idus.set_row(1,68)
    idus.set_row(3,24)
    idus.set_column('A:A',9)
    idus.set_column('B:F',18)
    idus.set_column('G:O',12,identity)
    idus.set_column('P:P',28,identity)
    idus.set_column('Q:BD',13)
    idus.set_column('BE:GS',12)
    idus.set_column('GT:GV',14)
    for row_number in (1, 2, 4):
        for col, value in enumerate(schema['headers'][str(row_number)]):
            if value:
                idus.write_string(row_number - 1, col, value,
                                  section if row_number==1 else (header if row_number==2 else subheader))

    idus_date_cols = {2, *FOLLOWUP_STARTS}
    for row_n, (code, item) in enumerate(by_code.items(), start=5):
        values = base_cells(item['new'].visit, row_n - 4)
        for i,op in enumerate(item['followups']):
            values.update(followup_cells(op.visit,FOLLOWUP_STARTS[i]))
        row_ix = row_n - 1
        for col,val in values.items():
            if val is None or val == '':
                continue
            if col in idus_date_cols:
                idus.write_number(row_ix,col,float(val),datefmt)
            elif col in set(range(6,16)):
                idus.write_string(row_ix,col,str(val),identity)
            elif isinstance(val, (int,float)) and not isinstance(val,bool):
                idus.write_number(row_ix,col,val,center)
            else:
                idus.write_string(row_ix,col,str(val))
        for col,formula in total_formulas(row_n).items():
            idus.write_formula(row_ix,col,formula)

    training = workbook.add_worksheet('TRAINING_RECORDS')
    training.freeze_panes(1, 0)
    training.set_tab_color('#13775F')
    training.set_row(0,25)
    training.write_row(0,0,_TRAINING_COLUMNS,header)
    training.set_column('A:A',39)
    training.set_column('B:B',15)
    training.set_column('C:C',33,identity)
    training.set_column('D:D',16)
    training.set_column('E:E',65,longtext)
    training.set_column('F:F',18)
    training.set_column('G:G',22)
    for line,op in enumerate(ops,start=1):
        payload = json.dumps(_payload(op.visit),ensure_ascii=False)
        row = [op.operation_id,
               'أول مرة' if op.kind=='NEW' else 'متابعة',
               op.code,op.visit.visit_date.isoformat(),payload,
               'APPROVED',worker_id]
        training.write_row(line,0,row)

    metadata = workbook.add_worksheet('TEST_INFO')
    metadata.set_column('A:A',24)
    metadata.set_column('B:B',95)
    metadata.write_row(0,0,['Environment','SYNTHETIC_ONLY'])
    metadata.write_row(1,0,['Approved submissions',len(ops)])
    if seed is not None:
        metadata.write_row(3,0,['Seed',seed])
    metadata.write(2,0,'Note')
    metadata.write(2,1,'SYNTHETIC TEST DATA - NOT FOR HIV PROGRAM INDICATORS. Import into LOCAL TEST/PILOT only.',title)

    workbook.close()
    return result.getvalue()
