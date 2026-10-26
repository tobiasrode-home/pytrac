"""Sicherer Import von PyTrac-JSON-Exporten mit ID-Zuordnung und Transaktion."""
from datetime import datetime
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as PydanticField
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

router=APIRouter(prefix="/api/data-import",tags=["Data Import"])
class ImportRequest(BaseModel):
    payload: dict
    dry_run: bool = True

CATEGORIES=("fields","tractors","implements","work_plannings","work_history")

def validate(payload):
    if payload.get("format")!="pytrac-export" or payload.get("version")!=1:
        raise ValueError("Keine unterstützte PyTrac-Exportdatei (Formatversion 1).")
    if not any(k in payload for k in CATEGORIES):
        raise ValueError("Die Datei enthält keine unterstützten Daten.")
    for key in CATEGORIES:
        if key in payload and not isinstance(payload[key],list):
            raise ValueError(f"{key} muss eine Liste sein.")
    if len(json.dumps(payload))>30_000_000:
        raise ValueError("Importdatei ist zu groß (max. 30 MB).")

def import_data(db,payload):
    validate(payload)
    counts={k:{"new":0,"existing":0} for k in CATEGORIES}
    maps={"tractors":{},"implements":{},"fields":{},"work_plannings":{}}
    for key,model,schema in (("tractors",Tractor,TractorCreate),("implements",Implement,ImplementCreate)):
        for raw in payload.get(key,[]):
            data=schema.model_validate(raw).model_dump()
            source_id=int(raw["id"])
            if source_id in maps[key]:raise ValueError(f"Doppelte ID in {key}: {source_id}")
            existing=db.scalar(select(model).where(model.name==data["name"]))
            if existing:
                counts[key]["existing"]+=1
                obj=existing
            else:
                obj=model(**data);db.add(obj);db.flush();counts[key]["new"]+=1
            maps[key][source_id]=obj.id
    for raw in payload.get("fields",[]):
        data=FieldCreate.model_validate(raw)
        source_id=int(raw["id"])
        if source_id in maps["fields"]:raise ValueError(f"Doppelte Feld-ID: {source_id}")
        existing=db.scalar(select(Field).where(Field.name==data.name))
        if existing:
            obj=existing;counts["fields"]["existing"]+=1
        else:
            service=FieldService(db)
            polygon=service._parse_boundary(data.boundary)
            service._validate_reference_line(data.reference_line)
            obj=Field(name=data.name,boundary_json=json.dumps(data.boundary),
                      reference_line_json=json.dumps(data.reference_line),
                      area_m2=service._area_m2(polygon))
            db.add(obj);db.flush()
            counts["fields"]["new"]+=1
        maps["fields"][source_id]=obj.id
    for raw in payload.get("work_plannings",[]):
        old_id=int(raw["id"])
        if old_id in maps["work_plannings"]:raise ValueError(f"Doppelte Arbeitsplan-ID: {old_id}")
        fk={}
        for key,col in (("tractors","tractor_id"),("implements","implement_id"),("fields","field_id")):
            original=int(raw[col])
            if original not in maps[key]:
                raise ValueError(f"Arbeitsplan {old_id}: {key} mit Export-ID {original} fehlt. Bitte vollständigen Export importieren.")
            fk[col]=maps[key][original]
        # Gleiche Export-ID wird nur bei identischem Arbeitsplan wiederverwendet.
        existing=db.get(WorkPlanning,old_id)
        if existing and existing.name==raw["name"] and all(getattr(existing,k)==v for k,v in fk.items()):
            obj=existing;counts["work_plannings"]["existing"]+=1
        else:
            allowed={c.name for c in WorkPlanning.__table__.columns}-{"id","tractor_id","implement_id","field_id","start_point_json","guidance_json","created_at"}
            attrs={k:raw[k] for k in allowed if k in raw}
            attrs.update(fk)
            attrs["start_point_json"]=json.dumps(raw.get("start_point",[]))
            attrs["guidance_json"]=json.dumps(raw["guidance"]) if "guidance" in raw else None
            if "created_at" in raw:attrs["created_at"]=datetime.fromisoformat(raw["created_at"].replace("Z","+00:00"))
            obj=WorkPlanning(**attrs);db.add(obj);db.flush();counts["work_plannings"]["new"]+=1
        maps["work_plannings"][old_id]=obj.id
    for group in payload.get("work_history",[]):
        old_plan=int(group["planning_id"])
        if old_plan not in maps["work_plannings"]:
            # Einzelner Historienexport: Zuordnung zu bereits vorhandenem Plan anhand ID.
            existing=db.get(WorkPlanning,old_plan)
            if existing and existing.name==group.get("planning_name"):
                maps["work_plannings"][old_plan]=existing.id
            else:raise ValueError(f"Arbeitshistorie: Arbeitsplan {old_plan} fehlt.")
        plan_id=maps["work_plannings"][old_plan]
        for point in group.get("points",[]):
            fix_key=str(point["fix_key"])
            existing=db.scalar(select(WorkProgressPoint.id).where(WorkProgressPoint.planning_id==plan_id,WorkProgressPoint.fix_key==fix_key))
            if existing is not None:counts["work_history"]["existing"]+=1;continue
            dt=datetime.fromisoformat(point["recorded_at"].replace("Z","+00:00"))
            db.add(WorkProgressPoint(planning_id=plan_id,fix_key=fix_key,recorded_at=dt,
                phase=point["phase"],track_id=str(point["track_id"]),
                latitude=float(point["latitude"]),longitude=float(point["longitude"]),
                speed_mps=point.get("speed_mps"),accuracy_m=point.get("accuracy_m")))
            counts["work_history"]["new"]+=1
    db.flush()
    return counts

@router.post("")
def import_export(data:ImportRequest,db:Session=Depends(get_db)):
    try:
        result=import_data(db,data.payload)
        if data.dry_run:db.rollback()
        else:db.commit()
        return {"dry_run":data.dry_run,"counts":result}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422,detail=str(exc)) from exc


@router.get("/work-plannings-export")
def export_plannings(db:Session=Depends(get_db)):
    from pytrac_core.services.work_planning_service import WorkPlanningService
    plans=WorkPlanningService(db).list()
    output=[]
    for item in plans:
        row=item.model_dump(mode="json") if hasattr(item,"model_dump") else dict(item)
        stored=db.get(WorkPlanning,row["id"])
        if stored and stored.guidance_json:
            row["guidance"]=json.loads(stored.guidance_json)
        output.append(row)
    return output
