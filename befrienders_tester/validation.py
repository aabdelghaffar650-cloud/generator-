"""Independent preflight checks against actual v0.5.2 core mapping."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from .rules import ACTORS, MAX_AGE, MIN_AGE, OUTREACH_NAMES, SYRINGE_STEP, visit_note
from .generator import CONDOM_STEP, LUBRICANT_STEP
from .reference_core import (base_cells, followup_cells, composite_code,
                             normalize_code, testing_fields, FOLLOWUP_STARTS, age_on)

@dataclass
class ValidationReport:
    errors: list[str]=field(default_factory=list)
    warnings: list[str]=field(default_factory=list)
    metrics: dict=field(default_factory=dict)

    @property
    def passed(self): return not self.errors

    def as_dict(self): return {'passed':self.passed,'errors':self.errors,
                              'warnings':self.warnings,'metrics':self.metrics}


def validate(operations, settings=None, existing_codes=()):
    report=ValidationReport()
    ops=list(operations)
    schedule=None
    if settings is not None and settings.schedule:
        from .generator import schedule_map
        try:
            schedule=schedule_map(settings)
        except ValueError as exc:
            report.errors.append(str(exc))
    existing={normalize_code(str(c)) for c in existing_codes if str(c).strip()}
    kinds=Counter(op.kind for op in ops)
    codes=defaultdict(list)
    identifiers=set()
    totals=Counter()
    service=Counter()
    first_dates={}
    female_new=0
    for i,op in enumerate(ops):
        try:
            code=normalize_code(composite_code(op.visit))
            if not code: raise ValueError('كود فارغ')
            if op.operation_id in identifiers:
                report.errors.append(f'[{i+1}] Operation ID مكرر')
            identifiers.add(op.operation_id)
            if op.kind not in ('NEW','FOLLOWUP'):
                report.errors.append(f'[{i+1}] نوع العملية غير صالح')
            if op.kind == 'NEW':
                base=base_cells(op.visit,1)
                for idx in (24,26,28,30,32,33,34,35,36,38,40,41,42,43,48,50):
                    if base.get(idx) not in ('نعم','لا'):
                        report.errors.append(f'[{i+1}] قيمة نعم/لا غير صحيحة في عمود {idx+1}')
                for q,pos in ((op.visit.condoms,24),(op.visit.lubricants,28),(op.visit.syringes,36)):
                    if q==0 and base[pos]!='لا':
                        report.errors.append(f'[{i+1}] كمية صفر مع خدمة مطلوبة')
                if code in existing:
                    report.errors.append(f'[{i+1}] كود موجود بالفعل في مرجع Pilot')
                if code in first_dates:
                    report.errors.append(f'[{i+1}] تكرار New لنفس الكود')
                first_dates[code]=op.visit.visit_date
                female_new += int(op.visit.gender == 'أنثى')
            else:
                followup_cells(op.visit,FOLLOWUP_STARTS[0])
                if op.kind=='FOLLOWUP' and code not in first_dates:
                    report.errors.append(f'[{i+1}] متابعة بدون زيارة أولى في المجموعة')
                if op.kind=='FOLLOWUP' and code in first_dates and op.visit.visit_date <= first_dates[code]:
                    report.errors.append(f'[{i+1}] تاريخ المتابعة ليس أحدث من أول زيارة')
            testing_fields(op.visit)
            if settings is not None and op.visit.gender not in ('ذكر','أنثى'):
                report.errors.append(f'[{i+1}] النوع غير صالح؛ يجب أن يكون ذكر أو أنثى')
            if settings is not None and not MIN_AGE <= age_on(op.visit.birth_date, op.visit.visit_date) <= MAX_AGE:
                report.errors.append(f'[{i+1}] السن خارج النطاق {MIN_AGE}–{MAX_AGE} في تاريخ الزيارة')
            if settings is not None and op.kind in ('NEW','FOLLOWUP') and op.visit.meeting_place != 'مقر الجمعية':
                report.errors.append(f'[{i+1}] مكان المقابلة غير مطابق لمقر الجمعية')
            codes[code].append(op)
            for name in ('syringes','condoms','lubricants'):
                value=getattr(op.visit,name)
                if type(value) is not int or value<0:raise ValueError(f'كمية غير صالحة: {name}')
                totals[name]+=value
            for name in ('syphilis','psychosocial'):
                service[name]+=int(getattr(op.visit,name))
            if op.visit.rapid_result=='سلبي':service['hiv_negative']+=1
            if op.visit.rapid_result=='إيجابي':service['hiv_positive']+=1
            if op.visit.confirm_result=='إيجابي':service['confirm_positive']+=1
            if settings is not None:
                if op.visit.syringes % SYRINGE_STEP:
                    report.errors.append(f'[{i+1}] السرنجات ليست من مضاعفات {SYRINGE_STEP}')
                skips_syringes = settings.syringe_people is not None and op.visit.syringes == 0
                if not skips_syringes and not (settings.minimum_syringes_per_visit <= op.visit.syringes
                                               <= settings.maximum_syringes_per_visit):
                    report.errors.append(f'[{i+1}] السرنجات خارج حدود الزيارة '
                                         f'({settings.minimum_syringes_per_visit}–{settings.maximum_syringes_per_visit})')
                if op.visit.condoms % CONDOM_STEP:
                    report.errors.append(f'[{i+1}] الواقيات ليست من مضاعفات {CONDOM_STEP}')
                if op.visit.lubricants % LUBRICANT_STEP:
                    report.errors.append(f'[{i+1}] المزلقات ليست من مضاعفات {LUBRICANT_STEP}')
                if op.visit.condoms > settings.maximum_condoms_per_visit:
                    report.errors.append(f'[{i+1}] الواقيات أكثر من الحد الأقصى للزيارة ({settings.maximum_condoms_per_visit})')
                if op.visit.lubricants > settings.maximum_lubricants_per_visit:
                    report.errors.append(f'[{i+1}] المزلقات أكثر من الحد الأقصى للزيارة ({settings.maximum_lubricants_per_visit})')
                if op.visit.lubricants and (op.visit.condoms == 0 or op.visit.lubricants != 2 * op.visit.condoms):
                    report.errors.append(f'[{i+1}] المزلق يجب أن يكون ضعف الواقي ولا يُعطى بدونه')
                if op.visit.notes != visit_note(op.visit.syringes, op.visit.condoms):
                    report.errors.append(f'[{i+1}] ملاحظات السرنجات والواقي غير مطابقة للقواعد')
                if op.visit.outreach_name not in OUTREACH_NAMES:
                    report.errors.append(f'[{i+1}] اسم المندوب غير معتمد')
                elif op.visit.actor != ACTORS[op.visit.outreach_name]:
                    report.errors.append(f'[{i+1}] actor لا يطابق المندوب')
                if not str(op.visit.area).strip():
                    report.errors.append(f'[{i+1}] منطقة الوصول فارغة')
                if schedule is not None:
                    expected_staff = schedule.get(op.visit.visit_date)
                    if expected_staff != (op.visit.outreach_name, op.visit.area):
                        report.errors.append(f'[{i+1}] المندوب/المنطقة لا يطابقان جدول يوم {op.visit.visit_date.isoformat()}')
        except (ValueError,AssertionError,TypeError) as exc:
            report.errors.append(f'[{i+1}] {exc}')
    for code,group in codes.items():
        count_new=sum(o.kind=='NEW' for o in group)
        count_follow=sum(o.kind=='FOLLOWUP' for o in group)
        if count_new>1 or count_follow>5:
            report.errors.append(f'تكرار غير مسموح للكود {code}')
        if count_new==0 and any(o.kind=='FOLLOWUP' for o in group):
            report.errors.append('متابعة بدون أصل')
        dates=[o.visit.visit_date for o in group]
        if len(dates)!=len(set(dates)):
            report.errors.append(f'زيارتان بنفس التاريخ للكود {code}')
    report.metrics={'unique_new_beneficiaries':kinds['NEW'],
      'followup_visits':kinds['FOLLOWUP'],
      'total_visits':len(ops),'unique_codes':len(codes),
      'female_new_beneficiaries':female_new,'male_new_beneficiaries':kinds['NEW']-female_new,
      'syringe_recipients':sum(o.visit.syringes>0 for o in ops),
      'condom_recipients':sum(o.visit.condoms>0 for o in ops),
      'lubricant_recipients':sum(o.visit.lubricants>0 for o in ops),
      **dict(totals),**dict(service)}
    if settings is not None:
        expected={'unique_new_beneficiaries':settings.beneficiaries,
                  'female_new_beneficiaries':settings.female_beneficiaries,
                  'followup_visits':round(settings.beneficiaries*settings.followup_percent/100),
                  'syringes':settings.syringes,'condoms':settings.condoms,
                  'hiv_negative':settings.hiv_negative,
                  'hiv_positive':settings.hiv_positive,'confirm_positive':settings.confirm_positive,
                  'syphilis':settings.syphilis,'psychosocial':settings.psychosocial}
        for key,value in expected.items():
            if report.metrics.get(key,0)!=value:
                report.errors.append(f'الإجمالي {key}: المتوقع {value}، الناتج {report.metrics.get(key,0)}')
        for key,wanted,label in (('syringe_recipients',settings.syringe_people,'السرنجات'),
                                 ('condom_recipients',settings.condom_people,'الواقي'),
                                 ('lubricant_recipients',settings.lubricant_people,'المزلق')):
            if wanted is not None and report.metrics[key]!=wanted:
                report.errors.append(f'عدد أشخاص {label}: المتوقع {wanted}، الناتج {report.metrics[key]}')
    return report
