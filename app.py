import streamlit as st
import hmac

def check_login():
    if st.session_state.get("authenticated", False):
        return

    st.title("تسجيل الدخول")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login = st.form_submit_button("Login")

    if login:
        valid_user = hmac.compare_digest(
            username, st.secrets["auth"]["username"]
        )
        valid_pass = hmac.compare_digest(
            password, st.secrets["auth"]["password"]
        )

        if valid_user and valid_pass:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("اسم المستخدم أو كلمة المرور غير صحيحة")

    st.stop()


check_login()

# باقي كود البرنامج يبدأ هنا
"""Arabic RTL UI. Offline: no network connections, no Google, no files linked."""
from __future__ import annotations
import os
import secrets
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from befrienders_tester.model import Settings, dump_operations
from befrienders_tester.generator import generate
from befrienders_tester.validation import validate
from befrienders_tester.exporter import csv_bytes, excel_bytes, report_bytes, visit_record
from befrienders_tester.training_export import training_excel_bytes
from befrienders_tester.roster import read_roster
from befrienders_tester.registry import DuplicateCodes, Registry, filter_registered
from befrienders_tester.rules import OUTREACH_NAMES, SYRINGE_MAX_DEFAULT, SYRINGE_MIN_DEFAULT, SYRINGE_STEP

COL_DATE, COL_OUTREACH, COL_AREA = 'التاريخ', 'المندوب', 'المنطقة'
REGISTRY_PATH = Path(os.environ.get('BEFRIENDERS_REGISTRY') or Path(__file__).resolve().parent / 'registry' / 'codes_registry.sqlite')
registry = Registry(REGISTRY_PATH)

st.set_page_config(page_title='Befrienders | Data Generator', page_icon='🧪', layout='wide')
st.markdown('''<style>
html, body, [data-testid="stApp"] {direction:rtl;font-family:Tahoma,Arial,sans-serif;}
[data-testid="stSidebar"] {direction:rtl;}
[data-testid="stMetric"] {background:#f2f7fa;border:1px solid #dfe8ed;border-radius:12px;padding:15px;}
.hero {background:linear-gradient(110deg,#12364a,#18718a);color:white;padding:24px;border-radius:16px;margin-bottom:14px;}
.hero h1 {color:white;font-size:2rem;margin:0 0 7px 0;}
.hero p{color:#d7edf5;margin:0;}
</style>''', unsafe_allow_html=True)
st.markdown('''<div class="hero"><h1>🧪 Befrienders Data Generator</h1>
<p>شيت المستفيدين ← أكواد من الأسماء ← جدول مناديب ومناطق لكل يوم ← زيارات وتوزيعات ← ملفات التصدير</p></div>''',
            unsafe_allow_html=True)
st.caption('يعمل محليًا بالكامل: لا اتصال بـGoogle ولا ربط بأي ملف أصلي. بيانات اختبار وتجارب فقط.')

for key, default in (('ops', []), ('settings', None), ('report', None), ('seed', None), ('sched_base', None),
                     ('sched_range', None), ('sched_ver', 0), ('registered_key', None), ('registered_batch', None)):
    st.session_state.setdefault(key, default)

# ---------------------------------------------------------------- 1. period + roster
st.subheader('1) فترة الزيارات وشيت المستفيدين')
c1, c2 = st.columns(2)
d_start = c1.date_input('بداية الفترة', value=date(2026, 11, 1))
d_end = c2.date_input('نهاية الفترة', value=date(2026, 11, 4))
uploaded = st.file_uploader('شيت Excel: العمود الأول الاسم الرباعي، الثاني تاريخ الميلاد، الثالث كود/اسم محافظة الميلاد',
                            type=['xlsx'])
people, roster_errors = [], []
if uploaded is not None and d_end > d_start:
    people, roster_errors = read_roster(uploaded.getvalue(), d_start, d_end)
    people, registry_errors = filter_registered(people, registry)
    roster_errors = roster_errors + registry_errors
    if registry_errors:
        st.warning(f'{len(registry_errors)} صف مرفوض لأن كوده مسجل في دفعات سابقة.')
    if people:
        st.success(f'تمت قراءة {len(people)} مستفيد بأكواد صالحة وفريدة.')
        with st.expander('معاينة الأكواد المستخرجة'):
            st.dataframe([{'صف': p.row, 'الاسم': p.name, 'الكود': p.code} for p in people[:200]],
                         use_container_width=True, hide_index=True)
    if roster_errors:
        st.error(f'{len(roster_errors)} صف مرفوض ولن يدخل التوليد (تكرار أو بيانات غير صالحة):')
        st.dataframe([{'الخطأ': e} for e in roster_errors[:200]], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- 2. schedule
st.subheader('2) مندوب ومنطقة الوصول لكل يوم')
if d_end <= d_start or (d_end - d_start).days < 2:
    st.error('الفترة لازم تكون 3 أيام على الأقل.')
    days = []
else:
    days = [d_start + timedelta(days=i) for i in range((d_end - d_start).days + 1)]
if days and st.session_state.sched_range != (d_start, d_end):
    st.session_state.sched_range = (d_start, d_end)
    st.session_state.sched_base = pd.DataFrame({COL_DATE: [d.isoformat() for d in days],
                                                COL_OUTREACH: [None] * len(days), COL_AREA: [''] * len(days)})
    st.session_state.sched_ver += 1
edited = None
if days:
    edited = st.data_editor(
        st.session_state.sched_base, key=f'sched_{st.session_state.sched_ver}', hide_index=True,
        use_container_width=True, disabled=[COL_DATE],
        column_config={COL_OUTREACH: st.column_config.SelectboxColumn(COL_OUTREACH, options=OUTREACH_NAMES),
                       COL_AREA: st.column_config.TextColumn(COL_AREA)})
    h1, h2, h3 = st.columns([2, 3, 2])
    fill_name = h1.selectbox('تعبئة سريعة: المندوب', OUTREACH_NAMES, key='fill_name')
    fill_area = h2.text_input('المنطقة', key='fill_area')
    if h3.button('تطبيق على الأيام الفارغة'):
        filled = edited.copy()
        empty = filled[COL_OUTREACH].isna() & (filled[COL_AREA].fillna('').str.strip() == '')
        filled.loc[empty, COL_OUTREACH] = fill_name
        filled.loc[empty, COL_AREA] = fill_area
        st.session_state.sched_base = filled
        st.session_state.sched_ver += 1
        st.rerun()

if days:
    with st.expander('⚡ إدخال سريع: اختر أيام كل مندوب (Multiselect) ومنطقته', expanded=True):
        st.caption('اختر لكل مندوب الأيام التي يعمل فيها ومنطقته، ثم «تطبيق على جدول الأيام». يمكنك بعدها تعديل أي يوم من الجدول أعلاه '
                   '(مثلًا لو نفس المندوب في منطقة مختلفة يوم معين). اليوم الواحد لا يمكن أن يكون لمندوبين.')
        picks = {}
        for name in OUTREACH_NAMES:
            m1, m2 = st.columns([3, 2])
            chosen = m1.multiselect(f'أيام {name}', days, format_func=lambda d: f'{d.day}/{d.month}',
                                    key=f'ms_{name}_{d_start}_{d_end}')
            area = m2.text_input(f'منطقة {name}', key=f'area_{name}_{d_start}_{d_end}')
            picks[name] = (chosen, area)
        owner, conflicts = {}, []
        for name, (chosen, _) in picks.items():
            for d in chosen:
                if d in owner:
                    conflicts.append(f'{d.day}/{d.month} ({owner[d]} و{name})')
                owner[d] = name
        if conflicts:
            st.error('أيام مكررة بين مندوبين: ' + '، '.join(conflicts))
        no_area = [name for name, (chosen, area) in picks.items() if chosen and not area.strip()]
        if no_area:
            st.warning('لم تُكتب منطقة لـ: ' + '، '.join(no_area))
        if st.button('تطبيق على جدول الأيام', key='apply_multiselect', disabled=bool(conflicts) or not owner):
            filled = edited.copy()
            for day, name in owner.items():
                row = filled[COL_DATE] == day.isoformat()
                filled.loc[row, COL_OUTREACH] = name
                filled.loc[row, COL_AREA] = picks[name][1].strip()
            st.session_state.sched_base = filled
            st.session_state.sched_ver += 1
            st.rerun()
        left = [d for d in days if d not in owner and edited.loc[edited[COL_DATE] == d.isoformat(), COL_OUTREACH].isna().all()]
        if left:
            st.caption('أيام لم يُحدَّد لها مندوب بعد: ' + '، '.join(f'{d.day}/{d.month}' for d in left))

# ---------------------------------------------------------------- 3. quantities
st.subheader('3) الكميات والخدمات')
n = len(people)
if n:
    st.caption(f'عدد المستفيدين الجدد = {n} (من الشيت). سرنجات كل زيارة من مضاعفات {SYRINGE_STEP} فقط '
               f'(30 / 60 / 90 / 120 / 150) فلا تظهر كسور، وأي زيارة أكثر من 90 تُكتب لها ملاحظة (الكمية ÷ 30). '
               'الواقي من مضاعفات 2 (2 / 4 / 6 / 8 …)، والمزلق دائمًا ضعف الواقي (فهو زوجي أيضًا).')
a, b, c = st.columns(3)
followup = a.slider('نسبة المستفيدين ذوي المتابعة', 0, 100, 0, 5,
                    help='المتابعة تحتاج 30 يومًا من الزيارة الأولى لتصدير Training.')
sheet_has_gender = bool(people) and all(p.gender for p in people)
sheet_females = sum(p.gender == 'أنثى' for p in people)
female = b.number_input('عدد السيدات من المستفيدين الجدد', min_value=0, max_value=max(n, 0),
                        value=sheet_females if sheet_has_gender else 0, step=1,
                        key=f'female_{n}_{sheet_females if sheet_has_gender else "x"}', disabled=sheet_has_gender,
                        help='لو الشيت فيه عمود النوع يُؤخذ منه تلقائيًا.')
auto_seed = c.checkbox('Seed تلقائي (موصى به)', value=True,
                       help='كل توليد يأخذ Seed جديدًا ويُسجَّل في الملفات. أوقفه فقط لإعادة نفس التوليد بالظبط.')
seed_input = c.number_input('Seed يدوي', min_value=0, value=20261031, step=1, disabled=auto_seed)
st.caption('«عدد الأشخاص» اختياري في كل أداة: لو تركته فارغًا يوزّع البرنامج الأداة على الزيارات تلقائيًا. '
           'الأعداد بالزيارات (تساوي عدد الأشخاص عندما لا توجد متابعات).')
x, y = st.columns(2)
syr = x.number_input('إجمالي السرنجات', min_value=0, value=n * 60 // SYRINGE_STEP * SYRINGE_STEP, step=SYRINGE_STEP,
                     key=f'syr_{n}')
syr_people = y.number_input('عدد أشخاص السرنجات (اختياري)', min_value=0, max_value=max(n, 1), value=None, step=1,
                            placeholder='الكل', key=f'syr_people_{n}')
x, y = st.columns(2)
con = x.number_input('إجمالي الواقيات الذكرية', min_value=0, value=n * 10, step=2, key=f'con_{n}')
con_people = y.number_input('عدد أشخاص الواقي (اختياري)', min_value=0, max_value=max(n, 1), value=None, step=1,
                            placeholder='بدون تحديد', key=f'con_people_{n}')
lub_people = st.number_input('عدد أشخاص المزلق (اختياري) — كل واحد يأخذ ضعف الواقي الذي أخذه', min_value=0,
                             max_value=max(n, 1), value=None, step=1, placeholder='بدون تحديد',
                             disabled=con_people is None, key=f'lub_people_{n}',
                             help='المزلق لا يُعطى إلا لمن أخذ واقيًا، وإجماليه يُحسب تلقائيًا. يتطلب تحديد عدد أشخاص الواقي أولًا.')
x, y, z = st.columns(3)
neg = x.number_input('HIV سريع سلبي', min_value=0, value=n, key=f'neg_{n}')
pos = y.number_input('HIV سريع إيجابي', min_value=0, value=0, key=f'pos_{n}')
confirm = z.number_input('إيجابي تأكيدي', min_value=0, value=0, key=f'conf_{n}')
x, y = st.columns(2)
syph = x.number_input('خدمة فحص الزهري', min_value=0, value=min(5, n), key=f'syph_{n}')
psy = y.number_input('خدمة دعم نفسي', min_value=0, value=min(2, n), key=f'psy_{n}')
w, x, y, z = st.columns(4)
limit_syr_min = w.number_input('أدنى سرنجات لكل زيارة', min_value=0, value=SYRINGE_MIN_DEFAULT, step=SYRINGE_STEP)
limit_syr = x.number_input('أقصى سرنجات لكل زيارة', min_value=0, value=SYRINGE_MAX_DEFAULT, step=SYRINGE_STEP)
limit_con = y.number_input('أقصى واقيات لكل زيارة', min_value=0, value=100, step=2)
limit_lub = z.number_input('أقصى مزلقات لكل زيارة', min_value=0, value=100, step=2,
                           help='المزلق ضعف الواقي، فمن يأخذ مزلقًا لا يزيد واقيه عن نصف هذا الحد.')
exclude = st.text_area('أكواد يجب استبعادها (اختياري؛ كود واحد بكل سطر)', height=70,
                       help='لو أحد أكواد الشيت موجود هنا يتوقف التوليد ويذكرها.')

ready = bool(people) and bool(days)
if st.button('🎲 توليد + فحص البيانات', type='primary', use_container_width=True, disabled=not ready):
    try:
        schedule = tuple((r[COL_DATE], r[COL_OUTREACH], r[COL_AREA]) for _, r in edited.iterrows()
                         if pd.notna(r[COL_OUTREACH]) or str(r[COL_AREA] or '').strip())
        seed = secrets.randbelow(10**9) if auto_seed else int(seed_input)
        optional = lambda v: None if v is None else int(v)
        s = Settings(n, int(syr), int(con), 0, int(neg), int(pos), int(confirm), int(syph), int(psy),
                     int(followup), seed, int(limit_syr), int(limit_con), int(limit_lub),
                     d_start.isoformat(), d_end.isoformat(), int(female), schedule,
                     minimum_syringes_per_visit=int(limit_syr_min), syringe_people=optional(syr_people),
                     condom_people=optional(con_people), lubricant_people=optional(lub_people))
        codes = [v.strip() for v in exclude.splitlines() if v.strip()]
        ops = generate(s, people, codes)
        report = validate(ops, s, codes)
        report.metrics['seed'] = seed
        st.session_state.update(ops=ops, settings=s, report=report, seed=seed)
        st.session_state.pop('xlsx_bytes', None)
        st.session_state.pop('training_xlsx_bytes', None)
        st.session_state.registered_key = None
        st.session_state.registered_batch = None
        if report.passed: st.success('نجح التحقق؛ الإجماليات صحيحة والأكواد فريدة وجدول الأيام مطبّق.')
        else: st.error('فشل التحقق؛ راجع الأخطاء أدناه.')
    except Exception as exc:
        st.session_state.update(ops=[], settings=None, report=None, seed=None)
        st.error(f'تعذر التوليد: {exc}')
elif not ready:
    st.info('ارفع الشيت وتأكد من الفترة، ثم املأ جدول الأيام لتفعيل التوليد.')

# ---------------------------------------------------------------- 4. results + exports
if st.session_state.ops and st.session_state.report:
    ops, rep, seed = st.session_state.ops, st.session_state.report, st.session_state.seed
    st.subheader('4) النتيجة والتصدير')
    st.caption(f'Seed المستخدم: {seed} (محفوظ داخل الملفات؛ اكتبه يدويًا لإعادة نفس التوليد).')
    for col, (title, key) in zip(st.columns(6), [('مستفيدون جدد', 'unique_new_beneficiaries'),
            ('سيدات', 'female_new_beneficiaries'), ('متابعات', 'followup_visits'), ('سرنجات', 'syringes'),
            ('واقيات', 'condoms'), ('مزلقات', 'lubricants')]):
        col.metric(title, rep.metrics.get(key, 0))
    st.dataframe([visit_record(o) for o in ops[:50]], use_container_width=True, hide_index=True)
    if rep.errors: st.error('\n'.join(rep.errors[:10]))
    if rep.warnings: st.warning(f'{len(rep.warnings)} تنبيه؛ أولها: ' + rep.warnings[0])
    new_codes = [o.code for o in ops if o.kind == 'NEW']
    batch_key = f'{seed}:{len(new_codes)}:{hash(tuple(new_codes))}'

    def register_batch():
        if st.session_state.registered_key == batch_key:
            return
        try:
            st.session_state.registered_batch = registry.register(new_codes, f'seed {seed} | {d_start} → {d_end}')
            st.session_state.registered_key = batch_key
        except DuplicateCodes as exc:
            st.session_state.registered_batch = f'خطأ: {exc}'

    auto_register = st.checkbox('تسجيل أكواد الدفعة تلقائيًا عند أول تنزيل (يمنع تكرارها في الرفعات القادمة)', value=True)
    on_download = register_batch if (auto_register and rep.passed) else None
    if st.session_state.registered_key == batch_key:
        st.success(f'الدفعة مسجّلة (رقم {st.session_state.registered_batch}): أي رفعة قادمة تحتوي هذه الأكواد ستُرفض.')
    else:
        st.info('الدفعة لم تُسجَّل بعد في سجل الأكواد، فلن تُمنع إعادة رفع نفس الأسماء حتى تُسجَّل.')
        if rep.passed and st.button('✅ تسجيل الدفعة الآن'):
            register_batch()
            st.rerun()
        if isinstance(st.session_state.registered_batch, str):
            st.error(st.session_state.registered_batch)
    a, b, c = st.columns(3)
    a.download_button('⬇️ CSV', csv_bytes(ops), 'befrienders_visits.csv', 'text/csv', on_click=on_download)
    b.download_button('⬇️ JSON', dump_operations(ops, seed), 'befrienders_visits.json', 'application/json',
                      on_click=on_download)
    c.download_button('⬇️ Validation Report', report_bytes(rep), 'validation_report.json', 'application/json',
                      on_click=on_download)
    if st.button('📗 تجهيز ملف Excel مع أعمدة IDUs الأصلية'):
        try:
            st.session_state['xlsx_bytes'] = excel_bytes(ops, rep)
        except Exception as exc: st.error(f'Excel export failed: {exc}')
    if st.session_state.get('xlsx_bytes'):
        st.download_button('⬇️ تنزيل Excel', st.session_state.xlsx_bytes, 'befrienders_IDUs.xlsx',
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', on_click=on_download)
    st.divider()
    st.markdown('**📘 Excel متوافق مع Training Pilot — نفس تبويبات الملف المعتمد**')
    st.caption('يتضمن IDUs وTRAINING_RECORDS وTEST_INFO. لا يرسل أي بيانات إلى Google.')
    worker_id = st.text_input('Training worker_id', value='outreach_1', key='training_worker_id')
    if st.button('📘 تجهيز Excel لرفع Training Pilot', disabled=not rep.passed):
        try:
            st.session_state['training_xlsx_bytes'] = training_excel_bytes(ops, worker_id=worker_id, seed=seed)
        except Exception as exc:
            st.error(f'تعذر تصدير Training: {exc}')
    if st.session_state.get('training_xlsx_bytes'):
        st.download_button('⬇️ تنزيل ملف Training المتوافق', st.session_state.training_xlsx_bytes,
                           'Befrienders_TRAINING_IDUs.xlsx',
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', on_click=on_download)


# ---------------------------------------------------------------- 5. code registry
st.divider()
with st.expander(f'🗂️ سجل الأكواد المسجلة ({registry.total_codes()} كود)'):
    st.caption('السجل يحفظ الأكواد فقط (بدون أسماء) في ملف محلي بجانب البرنامج: registry/codes_registry.sqlite. '
               'انسخه للاحتفاظ به أو نقله لجهاز آخر.')
    history = registry.batches()
    if history:
        st.dataframe([{'الدفعة': b['id'], 'التاريخ': b['created_at'], 'عدد الأكواد': b['code_count'],
                       'ملاحظة': b['note']} for b in history], use_container_width=True, hide_index=True)
        r1, r2 = st.columns(2)
        pick = r1.selectbox('حذف دفعة من السجل (لو سُجلت بالخطأ)', [b['id'] for b in history])
        if r1.checkbox('أؤكد حذف هذه الدفعة', key='confirm_delete') and r1.button('🗑️ حذف الدفعة'):
            registry.delete_batch(int(pick))
            st.session_state.registered_key = None
            st.rerun()
        if r2.checkbox('أؤكد مسح السجل بالكامل', key='confirm_clear') and r2.button('🧹 مسح كل السجل'):
            registry.clear()
            st.session_state.registered_key = None
            st.rerun()
    else:
        st.info('السجل فارغ.')
