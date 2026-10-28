"""PyTrac JSON import: independent categories, safe name-based FK resolution."""
from datetime import datetime
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from pytrac_core.persistence.database import get_db
from pytrac_core.persistence.models.tractor import Tractor
from pytrac_core.persistence.models.implement import Implement
from pytrac_core.persistence.models.field import Field
from pytrac_core.persistence.models.work_planning import WorkPlanning
from pytrac_core.persistence.models.work_progress import WorkProgressPoint
from pytrac_core.api.schemas import TractorCreate, ImplementCreate, FieldCreate
from pytrac_core.services.field_service import FieldService

router = APIRouter(prefix='/api/data-import', tags=['Data Import'])
CATEGORIES = ('fields', 'tractors', 'implements', 'work_plannings', 'work_history')

class ImportRequest(BaseModel):
    payload: dict
    dry_run: bool = True
    # Explicit permission to use unverified IDs in OLD, name-less exports.
    allow_legacy_id_matching: bool = False

def validate(payload):
    if payload.get('format') != 'pytrac-export' or payload.get('version') != 1:
        raise ValueError('Keine unterstützte PyTrac-Exportdatei (Formatversion 1).')
    if not any(k in payload for k in CATEGORIES):
        raise ValueError('Die Datei enthält keine unterstützten Daten.')
    for key in CATEGORIES:
        if key in payload and not isinstance(payload[key], list):
            raise ValueError(f'{key} muss eine Liste sein.')
    if len(json.dumps(payload)) > 30_000_000:
        raise ValueError('Importdatei ist zu groß (max. 30 MB).')

def import_data(db, payload, allow_legacy_id_matching=False):
    validate(payload)
    counts = {k: {'new': 0, 'existing': 0} for k in CATEGORIES}
    maps = {'tractors': {}, 'implements': {}, 'fields': {}, 'work_plannings': {}}
    warnings = []
    models = {'tractors': Tractor, 'implements': Implement, 'fields': Field}

    for key, model, schema in (('tractors', Tractor, TractorCreate), ('implements', Implement, ImplementCreate)):
        for raw in payload.get(key, []):
            data = schema.model_validate(raw).model_dump()
            source_id = int(raw['id'])
            if source_id in maps[key]:
                raise ValueError(f'Doppelte ID in {key}: {source_id}')
            existing = db.scalar(select(model).where(model.name == data['name']))
            if existing:
                counts[key]['existing'] += 1
                obj = existing
            else:
                obj = model(**data)
                db.add(obj)
                db.flush()
                counts[key]['new'] += 1
            maps[key][source_id] = obj.id

    for raw in payload.get('fields', []):
        data = FieldCreate.model_validate(raw)
        source_id = int(raw['id'])
        if source_id in maps['fields']:
            raise ValueError(f'Doppelte Feld-ID: {source_id}')
        existing = db.scalar(select(Field).where(Field.name == data.name))
        if existing:
            obj = existing
            counts['fields']['existing'] += 1
        else:
            service = FieldService(db)
            polygon = service._parse_boundary(data.boundary)
            service._validate_reference_line(data.reference_line)
            obj = Field(name=data.name, boundary_json=json.dumps(data.boundary),
                        reference_line_json=json.dumps(data.reference_line),
                        area_m2=service._area_m2(polygon))
            db.add(obj)
            db.flush()
            counts['fields']['new'] += 1
        maps['fields'][source_id] = obj.id

    def resolve_fk(raw, key, column, name_column):
        original = int(raw[column])
        model = models[key]
        if original in maps[key]:
            mapped = db.get(model, maps[key][original])
            expected = raw.get(name_column)
            if expected and mapped.name != expected:
                raise ValueError(f"Arbeitsplan {raw['id']}: {key} ID {original}: Name widerspricht Export ({expected!r} != {mapped.name!r}).")
            return mapped.id
        expected = raw.get(name_column)
        if expected:
            existing = db.scalar(select(model).where(model.name == expected))
            if not existing:
                raise ValueError(f"Arbeitsplan {raw['id']}: {key} '{expected}' fehlt. Bitte Stammdaten zuerst importieren.")
            maps[key][original] = existing.id
            return existing.id
        # Older exports contain ONLY IDs. Do not silently connect to an unrelated record.
        existing = db.get(model, original)
        if existing and allow_legacy_id_matching:
            warnings.append(f"Arbeitsplan {raw['id']}: {key} Export-ID {original} ohne Namen mit vorhandenem '{existing.name}' verknüpft. Bitte prüfen!")
            maps[key][original] = existing.id
            return existing.id
        if existing:
            raise ValueError(f"Arbeitsplan {raw['id']}: {key} Export-ID {original} hat keinen Namen. Für alte Exporte 'Legacy-ID-Zuordnung erlauben' aktivieren oder einen neuen Export mit Namen verwenden.")
        raise ValueError(f"Arbeitsplan {raw['id']}: {key} Export-ID {original} fehlt. Bitte Stammdaten zuerst importieren.")

    for raw in payload.get('work_plannings', []):
        old_id = int(raw['id'])
        if old_id in maps['work_plannings']:
            raise ValueError(f'Doppelte Arbeitsplan-ID: {old_id}')
        fk = {col: resolve_fk(raw, key, col, name) for key, col, name in (
            ('tractors', 'tractor_id', 'tractor_name'),
            ('implements', 'implement_id', 'implement_name'),
            ('fields', 'field_id', 'field_name'))}
        # Names are unique among plans; existing name with different dependencies is a conflict.
        existing_by_name = db.scalar(select(WorkPlanning).where(WorkPlanning.name == raw['name']))
        existing_by_id = db.get(WorkPlanning, old_id)
        if existing_by_name and all(getattr(existing_by_name, k) == v for k, v in fk.items()):
            obj = existing_by_name
            counts['work_plannings']['existing'] += 1
        elif existing_by_name:
            raise ValueError(f"Arbeitsplan '{raw['name']}' existiert bereits, aber mit anderen Stammdaten. Kein Überschreiben.")
        elif existing_by_id and existing_by_id.name == raw['name'] and all(getattr(existing_by_id, k) == v for k, v in fk.items()):
            obj = existing_by_id
            counts['work_plannings']['existing'] += 1
        else:
            allowed = {c.name for c in WorkPlanning.__table__.columns} - {'id', 'tractor_id', 'implement_id', 'field_id', 'start_point_json', 'guidance_json', 'created_at'}
            attrs = {k: raw[k] for k in allowed if k in raw}
            attrs.update(fk)
            attrs['start_point_json'] = json.dumps(raw.get('start_point', []))
            attrs['guidance_json'] = json.dumps(raw['guidance']) if 'guidance' in raw else None
            if 'created_at' in raw:
                attrs['created_at'] = datetime.fromisoformat(raw['created_at'].replace('Z', '+00:00'))
            obj = WorkPlanning(**attrs)
            db.add(obj)
            db.flush()
            counts['work_plannings']['new'] += 1
        maps['work_plannings'][old_id] = obj.id

    for group in payload.get('work_history', []):
        old_plan = int(group['planning_id'])
        if old_plan not in maps['work_plannings']:
            existing = db.get(WorkPlanning, old_plan)
            if existing and existing.name == group.get('planning_name'):
                maps['work_plannings'][old_plan] = existing.id
            else:
                named = db.scalar(select(WorkPlanning).where(WorkPlanning.name == group.get('planning_name'))) if group.get('planning_name') else None
                if named:
                    maps['work_plannings'][old_plan] = named.id
                else:
                    raise ValueError(f'Arbeitshistorie: Arbeitsplan {old_plan} fehlt.')
        plan_id = maps['work_plannings'][old_plan]
        for point in group.get('points', []):
            fix_key = str(point['fix_key'])
            existing = db.scalar(select(WorkProgressPoint.id).where(WorkProgressPoint.planning_id == plan_id, WorkProgressPoint.fix_key == fix_key))
            if existing is not None:
                counts['work_history']['existing'] += 1
                continue
            dt = datetime.fromisoformat(point['recorded_at'].replace('Z', '+00:00'))
            db.add(WorkProgressPoint(planning_id=plan_id, fix_key=fix_key, recorded_at=dt,
                phase=point['phase'], track_id=str(point['track_id']),
                latitude=float(point['latitude']), longitude=float(point['longitude']),
                speed_mps=point.get('speed_mps'), accuracy_m=point.get('accuracy_m')))
            counts['work_history']['new'] += 1
    db.flush()
    return counts, warnings

@router.post('')
def import_export(data: ImportRequest, db: Session = Depends(get_db)):
    try:
        counts, warnings = import_data(db, data.payload, data.allow_legacy_id_matching)
        if data.dry_run:
            db.rollback()
        else:
            db.commit()
        return {'dry_run': data.dry_run, 'counts': counts, 'warnings': warnings}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get('/work-plannings-export')
def export_plannings(db: Session = Depends(get_db)):
    from pytrac_core.services.work_planning_service import WorkPlanningService
    plans = WorkPlanningService(db).list()
    output = []
    for item in plans:
        row = item.model_dump(mode='json') if hasattr(item, 'model_dump') else dict(item)
        stored = db.get(WorkPlanning, row['id'])
        if stored and stored.guidance_json:
            row['guidance'] = json.loads(stored.guidance_json)
        for column, name, model in (('tractor_id', 'tractor_name', Tractor),
                                     ('implement_id', 'implement_name', Implement),
                                     ('field_id', 'field_name', Field)):
            linked = db.get(model, row[column])
            if linked:
                row[name] = linked.name
        output.append(row)
    return output
