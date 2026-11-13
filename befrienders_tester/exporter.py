"""CSV + Excel report exports. Excel created using artifact_tool, no input file changes."""
import csv
import io
import json
from collections import defaultdict
from datetime import date
from .model import TAG
from .reference_core import base_cells, followup_cells, FOLLOWUP_STARTS, total_formulas, age_on

FIELDS=['operation_id','kind','expected_row','code','visit_date','birth_date',
        'G_day','H_month','I_year','J_governorate','K_first1','L_first2','M_first3','N_last1','O_last2',
        'syringes','condoms','lubricants','rapid_result','confirm_result','linked_to_treatment',
        'syphilis','psychosocial','notes','synthetic_label',
        'gender','age_at_visit','meeting_place']


def visit_record(op):
    v=op.visit
    parts=[f'{v.birth_date.day:02d}',f'{v.birth_date.month:02d}',f'{v.birth_date.year%100:02d}',
           v.birth_governorate_code,*v.first3,*v.last2]
    return dict(zip(FIELDS,[op.operation_id,op.kind,op.expected_row or '',op.code,
         v.visit_date.isoformat(),v.birth_date.isoformat(),*parts,
         v.syringes,v.condoms,v.lubricants,v.rapid_result,v.confirm_result,
         'نعم' if (v.rapid_result=='إيجابي' and v.confirm_result=='إيجابي') else 'لا',
         'نعم' if v.syphilis else 'لا','نعم' if v.psychosocial else 'لا',v.notes,TAG,
         v.gender,age_on(v.birth_date,v.visit_date),v.meeting_place]))


def csv_bytes(ops):
    buffer=io.StringIO(newline='')
    w=csv.DictWriter(buffer,fieldnames=FIELDS)
    w.writeheader()
    w.writerows(visit_record(o) for o in ops)
    return ('\ufeff'+buffer.getvalue()).encode('utf-8')


def report_bytes(report):
    return json.dumps({'label':TAG,**report.as_dict()},ensure_ascii=False,indent=2).encode('utf-8')


def _col_name(idx):
    n=idx+1; s=''
    while n:
        n,rem=divmod(n-1,26)
        s=chr(65+rem)+s
    return s


def excel_bytes(ops,report):
    """Excel export with portable XlsxWriter (installable on Windows)."""
    import xlsxwriter
    import io
    from collections import OrderedDict
    output=io.BytesIO()
    wb=xlsxwriter.Workbook(output,{'in_memory':True})
    red=wb.add_format({'bold':True,'font_color':'white','bg_color':'#842029','text_wrap':True})
    blue=wb.add_format({'bold':True,'font_color':'white','bg_color':'#17496A','align':'center'})
    monospace=wb.add_format({'font_name':'Consolas'})
    datefmt=wb.add_format({'num_format':'dd/mm/yyyy'})
    layout=wb.add_worksheet('IDUs_SYNTHETIC')
    layout.right_to_left()
    layout.set_tab_color('#C63C4A')
    layout.freeze_panes(4,0)
    layout.set_column(6,8,12)
    layout.set_column(15,15,30,monospace)
    layout.write(0,0,TAG,red)
    layout.write(1,0,'TEST ONLY — NOT FOR OFFICIAL REPORTING',red)
    layout.write(1,1,'Original IDUs column positions')
    layout.write(2,0,'Mapping: G/H/I birth; J governorate; K:O name letters; P code')
    layout.set_row(3,22)
    layout.write_row(3,0,[_col_name(i) for i in range(204)],blue)
    by_code=OrderedDict()
    for op in ops:
        if op.kind=='NEW':by_code[op.code]={'new':op,'followups':[]}
        elif op.kind=='FOLLOWUP' and op.code in by_code:
            by_code[op.code]['followups'].append(op)
    for excel_index,(code,entry) in enumerate(by_code.items(),start=5):
        row_idx=excel_index-1
        row=['']*204
        row_map=base_cells(entry['new'].visit,excel_index-4)
        for col,value in row_map.items():row[col]=value
        for j,op in enumerate(entry['followups'][:5]):
            for col,value in followup_cells(op.visit,FOLLOWUP_STARTS[j]).items():row[col]=value
        for col,val in enumerate(row):
            if val=='':continue
            if col in [6,7,8] or col in list(range(9,16)):
                layout.write_string(row_idx,col,str(val))
            elif col in [2,*FOLLOWUP_STARTS] and isinstance(val,(int,float)):
                layout.write_number(row_idx,col,val,datefmt)
            elif isinstance(val,(int,float)):
                layout.write_number(row_idx,col,val)
            else:layout.write_string(row_idx,col,str(val))
        for col,formula in total_formulas(excel_index).items():
            layout.write_formula(row_idx,col,formula)
    operations=wb.add_worksheet('OPERATIONS')
    operations.right_to_left()
    operations.freeze_panes(1,0)
    operations.set_row(0,27)
    operations.write_row(0,0,FIELDS,blue)
    operations.set_column(3,3,31)
    operations.set_column(23,24,44)
    for row_idx,op in enumerate(ops,1):
        record=visit_record(op)
        for col,key in enumerate(FIELDS):
            value=record[key]
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                operations.write_number(row_idx,col,value)
            else:
                operations.write_string(row_idx,col,str(value))
    validation=wb.add_worksheet('VALIDATION')
    validation.right_to_left()
    validation.set_column(0,0,38)
    validation.set_column(1,1,80)
    details=[['TEST DATA / NOT FOR OFFICIAL REPORTING',''],
             ['Result','PASS' if report.passed else 'FAIL'],
             ['Errors',len(report.errors)],['Warnings',len(report.warnings)]]
    details += [[k,v] for k,v in report.metrics.items()]
    details += [['ERROR',e] for e in report.errors]+[['WARNING',w] for w in report.warnings]
    for ridx,(key,val) in enumerate(details):
        validation.write_string(ridx,0,str(key),red if ridx==0 else None)
        if isinstance(val,(int,float)):validation.write_number(ridx,1,val)
        else:validation.write_string(ridx,1,str(val))
    readme=wb.add_worksheet('READ_ME')
    readme.set_column(0,0,35);readme.set_column(1,1,82)
    for i,values in enumerate([
        ['NOTICE',TAG],['Purpose','Synthetic testing only'],
        ['Original IDUs mapping','G:O identity parts; P code; BE:GS follow-up'],
        ['Historical data','Never included in IDUs_SYNTHETIC'],
        ['Reporting','Do not merge into official M&E or HIV reports']]):
        readme.write_row(i,0,values,red if i==0 else None)
    wb.close()
    return output.getvalue()
