"""Deterministic visit generation for an uploaded roster (no live data, no network)."""
import hashlib
import json
import random
import uuid
from dataclasses import asdict, replace
from datetime import date, timedelta
from .model import Operation, Settings
from .reference_core import Visit, composite_code, normalize_code
from .rules import ACTORS, OUTREACH_NAMES, SYRINGE_STEP, condom_note, visit_note

DEFAULT_MEETING_PLACE = 'مقر الجمعية'
CONDOM_STEP = 2      # condoms: any even number (2, 4, 6, 8 ...)
LUBRICANT_STEP = 2   # lubricant = 2 x condoms, so it is always even too (a multiple of 4)


def distribute_exact(total: int, count: int, cap: int, rng: random.Random) -> list[int]:
    """Weighted stochastic allocation, with exact conservation and per-visit cap."""
    if total < 0 or count < 0 or cap < 0 or total > count * cap:
        raise ValueError('الإجمالي يتجاوز السعة المسموح بها لعدد الزيارات')
    if not count:
        if total: raise ValueError('لا يمكن توزيع إجمالي على صفر زيارات')
        return []
    weights = [rng.gammavariate(2.0, 1.0) + 0.01 for _ in range(count)]
    allocated = [0] * count
    pending = total
    while pending:
        candidates = [i for i in range(count) if allocated[i] < cap]
        all_weight = sum(weights[i] for i in candidates)
        fractional = [(pending * weights[i] / all_weight, i) for i in candidates]
        given = 0
        for share, i in fractional:
            amount = min(cap-allocated[i],int(share))
            allocated[i] += amount
            given += amount
        pending -= given
        if pending == 0: break
        if given == 0:
            pick = rng.choices(candidates, weights=[weights[i] for i in candidates], k=1)[0]
            allocated[pick] += 1
            pending -= 1
    assert sum(allocated) == total
    return allocated


def _allocate(total_units: int, m: int, recipients, lo_units: int, hi_units: int, rng: random.Random) -> list[int]:
    """Units per visit. `recipients` visits (None = all) get lo..hi units each; the others get 0."""
    if recipients is None or recipients == m:
        extra = distribute_exact(total_units - lo_units * m, m, hi_units - lo_units, rng)
        return [lo_units + u for u in extra]
    chosen = sorted(rng.sample(range(m), recipients))
    extra = iter(distribute_exact(total_units - lo_units * recipients, recipients, hi_units - lo_units, rng)
                 if recipients else [])
    amounts = [0] * m
    for i in chosen:
        amounts[i] = lo_units + next(extra)
    return amounts


def distribute_with_caps(total: int, caps: list[int], rng: random.Random) -> list[int]:
    """Same stochastic allocation as distribute_exact, but every item has its own cap."""
    count = len(caps)
    if total < 0 or any(c < 0 for c in caps) or total > sum(caps):
        raise ValueError('الإجمالي يتجاوز السعة المسموح بها لعدد الزيارات')
    if not count:
        return []
    weights = [rng.gammavariate(2.0, 1.0) + 0.01 for _ in range(count)]
    allocated = [0] * count
    pending = total
    while pending:
        candidates = [i for i in range(count) if allocated[i] < caps[i]]
        all_weight = sum(weights[i] for i in candidates)
        given = 0
        for i in candidates:
            amount = min(caps[i] - allocated[i], int(pending * weights[i] / all_weight))
            allocated[i] += amount
            given += amount
        pending -= given
        if pending == 0: break
        if given == 0:
            pick = rng.choices(candidates, weights=[weights[i] for i in candidates], k=1)[0]
            allocated[pick] += 1
            pending -= 1
    assert sum(allocated) == total
    return allocated


def build_notes(syringes: int, condoms: int) -> str:
    """Use exactly the same note builder as preflight validation."""
    return visit_note(syringes, condoms)


def lubricant_condom_cap_units(settings: Settings) -> int:
    """Lubricant = 2 x condoms and cannot exceed its per-visit maximum, so a lubricant taker's condoms
    are capped at half of that maximum (in steps of 5 condoms)."""
    return settings.maximum_lubricants_per_visit // (2 * CONDOM_STEP)


def schedule_map(settings: Settings) -> dict:
    """{date: (outreach, area)}; every day of the window must be assigned."""
    start, end = date.fromisoformat(settings.visit_start), date.fromisoformat(settings.visit_end)
    mapping = {}
    for item in settings.schedule:
        day, outreach, area = item
        outreach, area = str(outreach or '').strip(), str(area or '').strip()
        if outreach not in OUTREACH_NAMES:
            raise ValueError(f'مندوب غير معتمد في جدول الأيام: «{outreach}»')
        if not area:
            raise ValueError(f'منطقة الوصول فارغة ليوم {day}')
        mapping[date.fromisoformat(str(day))] = (outreach, area)
    missing = [(start + timedelta(days=i)).isoformat() for i in range((end-start).days + 1)
               if (start + timedelta(days=i)) not in mapping]
    if missing:
        raise ValueError('جدول الأيام ناقص: ' + '، '.join(missing[:6]) + ('…' if len(missing) > 6 else ''))
    return mapping


def _optional_count(label, value, m):
    """Optional 'number of people' input: None = not given."""
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= m:
        raise ValueError(f'عدد أشخاص {label} يجب أن يكون من 0 إلى {m}')
    return value


def _validate_settings(s: Settings, roster_size: int):
    n = s.beneficiaries
    if n != roster_size: raise ValueError('عدد المستفيدين يجب أن يساوي عدد صفوف الشيت')
    if not 1 <= n <= 10000: raise ValueError('عدد المستفيدين يجب أن يكون بين 1 و10000')
    if type(s.female_beneficiaries) is not int or not 0 <= s.female_beneficiaries <= n:
        raise ValueError('عدد السيدات يجب أن يكون من صفر إلى إجمالي المستفيدين الجدد')
    if not 0 <= s.followup_percent <= 100: raise ValueError('نسبة المتابعات يجب أن تكون 0 إلى 100')
    m = n + round(n*s.followup_percent/100)
    for field in ('syringes','condoms','hiv_negative','hiv_positive','confirm_positive','syphilis','psychosocial'):
        if getattr(s,field) < 0: raise ValueError(f'قيمة سالبة: {field}')
    if s.hiv_negative + s.hiv_positive > m: raise ValueError('عدد تحاليل HIV أكبر من عدد الزيارات')
    if s.confirm_positive > s.hiv_positive: raise ValueError('التأكيدي الإيجابي أكبر من السريع الإيجابي')
    if s.syphilis > m or s.psychosocial > m: raise ValueError('الخدمات أكبر من عدد الزيارات')
    date1, date2 = date.fromisoformat(s.visit_start), date.fromisoformat(s.visit_end)
    if date2 <= date1 or (date2-date1).days < 2: raise ValueError('فترة الزيارات يجب ألا تقل عن 3 أيام')
    syringe_visits = _optional_count('السرنجات', s.syringe_people, m)
    condom_visits = _optional_count('الواقي', s.condom_people, m)
    lubricant_visits = _optional_count('المزلق', s.lubricant_people, m)
    lo, hi = s.minimum_syringes_per_visit, s.maximum_syringes_per_visit
    if s.syringes % SYRINGE_STEP:
        raise ValueError(f'إجمالي السرنجات يجب أن يكون من مضاعفات {SYRINGE_STEP}')
    if lo % SYRINGE_STEP or hi % SYRINGE_STEP or lo < 0 or lo > hi:
        raise ValueError(f'حدّا السرنجات في الزيارة يجب أن يكونا من مضاعفات {SYRINGE_STEP} والحد الأدنى لا يزيد عن الأقصى')
    takers = m if syringe_visits is None else syringe_visits
    if not lo * takers <= s.syringes <= hi * takers:
        raise ValueError(f'إجمالي السرنجات لا يمكن توزيعه على {takers} زيارة بين {lo} و{hi}: '
                         f'يجب أن يكون بين {lo * takers} و{hi * takers}')
    cap = s.maximum_condoms_per_visit
    if s.condoms % CONDOM_STEP:
        raise ValueError(f'إجمالي الواقيات يجب أن يكون من مضاعفات {CONDOM_STEP}')
    if cap < 0 or cap % CONDOM_STEP:
        raise ValueError(f'الحد الأقصى للواقيات في الزيارة يجب أن يكون من مضاعفات {CONDOM_STEP}')
    if condom_visits is None:
        if s.condoms > cap * m:
            raise ValueError(f'إجمالي الواقيات لا يمكن توزيعه على {m} زيارة بالحد الأقصى المحدد: يجب ألا يزيد عن {cap * m}')
    elif not CONDOM_STEP * condom_visits <= s.condoms <= cap * condom_visits:
        raise ValueError(f'إجمالي الواقيات لا يمكن توزيعه على {condom_visits} شخص: '
                         f'يجب أن يكون بين {CONDOM_STEP * condom_visits} و{cap * condom_visits}')
    lub_cap = s.maximum_lubricants_per_visit
    if lub_cap < 0 or lub_cap % LUBRICANT_STEP:
        raise ValueError(f'الحد الأقصى للمزلقات في الزيارة يجب أن يكون من مضاعفات {LUBRICANT_STEP}')
    if lubricant_visits is not None:
        if condom_visits is None:
            raise ValueError('حدد عدد أشخاص الواقي أولًا: المزلق لا يُعطى إلا لمن أخذ واقيًا')
        if lubricant_visits > condom_visits:
            raise ValueError(f'عدد من يأخذ المزلق ({lubricant_visits}) أكبر من عدد من يأخذ الواقي ({condom_visits})')
        lub_units = lubricant_condom_cap_units(s)
        if lubricant_visits and lub_units < 1:
            raise ValueError(f'الحد الأقصى للمزلقات في الزيارة أقل من {2 * CONDOM_STEP}، فلا يمكن إعطاء مزلق (المزلق ضعف الواقي)')
        room = (condom_visits - lubricant_visits) * (cap // CONDOM_STEP) + lubricant_visits * min(cap // CONDOM_STEP, lub_units)
        if s.condoms // CONDOM_STEP > room:
            raise ValueError(
                f'إجمالي الواقيات لا يمكن توزيعه: من يأخذ المزلق ({lubricant_visits}) لا يزيد واقيه عن '
                f'{min(cap // CONDOM_STEP, lub_units) * CONDOM_STEP} (نصف الحد الأقصى للمزلق {lub_cap}). '
                f'أقصى إجمالي ممكن {room * CONDOM_STEP}')
    return m


def generate(settings: Settings, roster, existing_codes=()):
    """Every roster person gets one NEW visit; followup_percent adds follow-ups to some of them."""
    roster = list(roster)
    m = _validate_settings(settings, len(roster))
    schedule = schedule_map(settings)
    rng = random.Random(settings.seed)
    exclusion = {normalize_code(str(x)) for x in existing_codes if str(x).strip()}
    clash = [p.code for p in roster if p.code in exclusion]
    if clash:
        raise ValueError('أكواد موجودة بالفعل في قائمة الاستبعاد: ' + '، '.join(clash[:5]))
    start, end = date.fromisoformat(settings.visit_start), date.fromisoformat(settings.visit_end)
    window = (end-start).days
    n = settings.beneficiaries
    followup_n = round(n * settings.followup_percent / 100)
    followup_indices = set(rng.sample(range(n), followup_n))
    days = window + 1
    if n >= days:
        day_offsets = list(range(days)) + [rng.randrange(days) for _ in range(n-days)]
    elif n == 1:
        day_offsets = [0]
    else:
        day_offsets = [0, window] + rng.sample(range(1, window), n-2)
    rng.shuffle(day_offsets)
    # The last day is reached by a NEW visit without follow-up whenever possible.
    for i in [i for i in followup_indices if day_offsets[i] == window]:
        alternatives = [j for j in range(n) if j not in followup_indices and day_offsets[j] < window]
        if alternatives:
            j = rng.choice(alternatives)
            day_offsets[i], day_offsets[j] = day_offsets[j], day_offsets[i]
        else:
            day_offsets[i] = window - 1

    if roster and all(p.gender for p in roster):
        female_indices = {i for i, p in enumerate(roster) if p.gender == 'أنثى'}
        if settings.female_beneficiaries != len(female_indices):
            raise ValueError('عدد السيدات يجب أن يطابق عمود النوع في الشيت')
    else:
        female_indices = set(rng.sample(range(n), settings.female_beneficiaries))

    def staffed(visit, day):
        outreach, area = schedule[day]
        return replace(visit, visit_date=day, outreach_name=outreach, area=area, actor=ACTORS[outreach])

    visits = []
    for idx, person in enumerate(roster):
        first_date = start + timedelta(days=day_offsets[idx])
        base = Visit(first_date, person.birth_date, person.gov, person.first3, person.last2,
                     '', 'الجيزة', '', DEFAULT_MEETING_PLACE,
                     'أنثى' if idx in female_indices else 'ذكر', rapid_result='لم يتم', notes='')
        visits.append(staffed(base, first_date))
    followups = []
    for idx in sorted(followup_indices):
        original = visits[idx]
        after = (end-original.visit_date).days
        followups.append(staffed(original, original.visit_date + timedelta(days=rng.randint(1, after))))
    if followups and followup_n == n:
        followups[0] = staffed(followups[0], end)
    all_visits = visits + followups
    assert len(all_visits) == m
    lo_units, hi_units = settings.minimum_syringes_per_visit // SYRINGE_STEP, settings.maximum_syringes_per_visit // SYRINGE_STEP
    syr = [u * SYRINGE_STEP for u in _allocate(settings.syringes // SYRINGE_STEP, m, settings.syringe_people,
                                                lo_units, hi_units, rng)]
    # Condoms and lubricant. Lubricant goes only to visits that took condoms and is always 2x that visit's
    # condoms, so a lubricant taker's condoms are capped at half of the lubricant maximum.
    cap_units = settings.maximum_condoms_per_visit // CONDOM_STEP
    lub_units = lubricant_condom_cap_units(settings)
    total_units = settings.condoms // CONDOM_STEP
    if settings.condom_people is not None:
        # The number of people is given: each of them gets at least one step (5).
        c = settings.condom_people
        chosen = sorted(rng.sample(range(m), c)) if c != m else list(range(m))
        lubricant_n = settings.lubricant_people
        if lubricant_n is None:
            lubricant_n = max(1, round(c * rng.uniform(0.5, 0.8))) if c and lub_units >= 1 else 0
            while lubricant_n and total_units > (c - lubricant_n) * cap_units + lubricant_n * min(cap_units, lub_units):
                lubricant_n -= 1
        lubricant_set = set(rng.sample(chosen, lubricant_n))
        caps = [min(cap_units, lub_units) if i in lubricant_set else cap_units for i in chosen]
        extra = distribute_with_caps(total_units - c, [cap - 1 for cap in caps], rng) if c else []
        con = [0] * m
        for i, units in zip(chosen, extra):
            con[i] = (1 + units) * CONDOM_STEP
    else:
        # No number given: spread the total over all visits; some visits may take none.
        con = [u * CONDOM_STEP for u in _allocate(total_units, m, None, 0, cap_units, rng)]
        eligible = [i for i in range(m) if con[i] > 0 and con[i] // CONDOM_STEP <= lub_units]
        takers = sum(1 for x in con if x > 0)
        lubricant_n = min(len(eligible), max(1, round(takers * rng.uniform(0.5, 0.8)))) if eligible else 0
        lubricant_set = set(rng.sample(eligible, lubricant_n))
    lub = [2 * con[i] if i in lubricant_set else 0 for i in range(m)]
    shuffled = list(range(m)); rng.shuffle(shuffled)
    neg = set(shuffled[:settings.hiv_negative])
    pos = set(shuffled[settings.hiv_negative:settings.hiv_negative+settings.hiv_positive])
    confirmed_pos = set(rng.sample(sorted(pos), settings.confirm_positive))
    rng.shuffle(shuffled)
    syph = set(shuffled[:settings.syphilis]); rng.shuffle(shuffled)
    psycho = set(shuffled[:settings.psychosocial])
    fingerprint = hashlib.sha256(json.dumps(asdict(settings), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    operations = []
    for i, v in enumerate(all_visits):
        rapid = 'سلبي' if i in neg else ('إيجابي' if i in pos else 'لم يتم')
        confirm = 'إيجابي' if i in confirmed_pos else ('سلبي' if i in pos else '')
        v = replace(v, syringes=syr[i], condoms=con[i], lubricants=lub[i],
                    rapid_result=rapid, confirm_result=confirm,
                    syphilis=i in syph, psychosocial=i in psycho, notes=build_notes(syr[i], con[i]))
        kind = 'NEW' if i < n else 'FOLLOWUP'
        op_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'befrienders:{fingerprint}:{i}:{kind}:{composite_code(v)}'))
        operations.append(Operation(op_id, kind, v))
    operations.sort(key=lambda o: (o.visit.visit_date, 0 if o.kind == 'NEW' else 1, o.operation_id))
    return operations
