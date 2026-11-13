"""Strongly typed, serialisable synthetic test fixtures."""
from dataclasses import dataclass, asdict
from datetime import date
import json
from .reference_core import Visit, composite_code

TAG = 'SYNTHETIC TEST DATA - NOT FOR OFFICIAL REPORTING'

@dataclass(frozen=True)
class Settings:
    beneficiaries: int = 200
    syringes: int = 10000
    condoms: int = 2000
    lubricants: int = 4000
    hiv_negative: int = 190
    hiv_positive: int = 0
    confirm_positive: int = 0
    syphilis: int = 5
    psychosocial: int = 2
    followup_percent: int = 0
    seed: int = 20261031
    maximum_syringes_per_visit: int = 150
    maximum_condoms_per_visit: int = 100
    maximum_lubricants_per_visit: int = 100
    visit_start: str = '2026-10-01'
    visit_end: str = '2026-10-31'
    female_beneficiaries: int = 0  # Count of female NEW beneficiaries; their follow-ups preserve gender
    # One (ISO date, outreach name, area) entry for every day of the visit window.
    schedule: tuple = ()
    minimum_syringes_per_visit: int = 30
    # Optional: how many visits receive each item (None = distribute over all visits as before).
    # Lubricant is always 2x that visit's condoms and only goes to visits that also take condoms,
    # so `lubricants` (total) is derived and ignored as an input.
    syringe_people: int | None = None
    condom_people: int | None = None
    lubricant_people: int | None = None

@dataclass(frozen=True)
class Operation:
    operation_id: str
    kind: str  # NEW / FOLLOWUP / HISTORICAL_FOLLOWUP
    visit: Visit
    expected_row: int | None = None

    @property
    def code(self):
        return composite_code(self.visit)

    def as_dict(self):
        v = asdict(self.visit)
        v['visit_date'] = self.visit.visit_date.isoformat()
        v['birth_date'] = self.visit.birth_date.isoformat()
        return {'operation_id': self.operation_id, 'kind': self.kind,
                'expected_row': self.expected_row, 'visit': v}

    @staticmethod
    def from_dict(data):
        payload = dict(data['visit'])
        payload['birth_date'] = date.fromisoformat(payload['birth_date'])
        payload['visit_date'] = date.fromisoformat(payload['visit_date'])
        payload['first3'] = tuple(payload['first3'])
        payload['last2'] = tuple(payload['last2'])
        return Operation(data['operation_id'],data['kind'],Visit(**payload),data.get('expected_row'))

def dump_operations(operations, seed=None):
    payload = {'label': TAG}
    if seed is not None:
        payload['seed'] = seed
    payload['operations'] = [o.as_dict() for o in operations]
    return json.dumps(payload, ensure_ascii=False, indent=2)

def load_operations(raw):
    obj = json.loads(raw)
    if obj.get('label') != TAG:
        raise ValueError('Not an explicitly labelled synthetic dataset')
    return [Operation.from_dict(v) for v in obj['operations']]
