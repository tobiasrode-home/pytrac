"""Frontend-unabhängige Berechnungen für Arbeitsplanung."""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import transform
from pyproj import CRS, Transformer
from pytrac_core.persistence.models.tractor import Tractor
from pytrac_core.persistence.models.implement import Implement
from pytrac_core.persistence.models.field import Field
from pytrac_core.persistence.models.work_planning import WorkPlanning
from pytrac_core.api.schemas import WorkPlanningDefaults, WorkPlanningPreview, WorkPlanningRead

class WorkPlanningValidationError(ValueError): pass
class WorkPlanningNotFoundError(LookupError): pass

class WorkPlanningService:
    def __init__(self, db: Session): self.db = db

    @staticmethod
    def calculate_headland_widths(tractor_length: float, implement_length: float, working_width: float) -> int:
        if not all(math.isfinite(x) and x > 0 for x in (tractor_length, implement_length, working_width)):
            raise WorkPlanningValidationError('Längen und Arbeitsbreite müssen positive, endliche Zahlen sein.')
        return max(1, math.ceil((tractor_length + implement_length) / working_width - 1e-12))

    def _data(self, tractor_id, implement_id, field_id=None):
        tractor = self.db.get(Tractor, tractor_id)
        implement = self.db.get(Implement, implement_id)
        field = self.db.get(Field, field_id) if field_id is not None else None
        if tractor is None or implement is None or (field_id is not None and field is None):
            raise WorkPlanningValidationError('Traktor, Anbaugerät oder Feld existiert nicht.')
        return tractor, implement, field

    def defaults(self, data):
        t, i, _ = self._data(data.tractor_id, data.implement_id)
        return WorkPlanningDefaults(tractor_length=t.length_m, implement_length=i.length_m,
            working_width=i.working_width_m,
            default_headland_working_widths=self.calculate_headland_widths(t.length_m, i.length_m, i.working_width_m))

    @staticmethod
    def _edges(field):
        coordinates = json.loads(field.boundary_json)
        if len(coordinates) < 4 or coordinates[0] != coordinates[-1]:
            raise WorkPlanningValidationError('Die Feldgrenze muss geschlossen sein.')
        if not Polygon(coordinates).is_valid:
            raise WorkPlanningValidationError('Die Feldgrenze ist geometrisch ungültig.')
        return coordinates[:-1]

    @staticmethod
    def _edge_index(edge_id, count):
        try:
            prefix, number = edge_id.split('-', 1)
            idx = int(number)
            if prefix != 'edge' or str(idx) != number or not 0 <= idx < count:
                raise ValueError()
            return idx
        except (ValueError, AttributeError):
            raise WorkPlanningValidationError(f'Ungültige Feldkante: {edge_id}')

    @staticmethod
    def _projector(points):
        lon = sum(p[0] for p in points) / len(points)
        lat = sum(p[1] for p in points) / len(points)
        local = CRS.from_proj4(f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs')
        forward = Transformer.from_crs('EPSG:4326', local, always_xy=True).transform
        inverse = Transformer.from_crs(local, 'EPSG:4326', always_xy=True).transform
        return forward, inverse

    def _geometry(self, data, field, working_width):
        """Ermittelt den ersten gültigen Fahrspur-Anfang im Start-Eckbereich.

        Geometrie ist bewusst eine erste Parallelspurplanung, keine vollständige
        Wende-/Spurführungsberechnung. Vorgewende wird als Innenabstand berücksichtigt.
        """
        vertices = self._edges(field)
        n = len(vertices)
        a = self._edge_index(data.alignment_boundary_id, n)
        b = self._edge_index(data.start_boundary_a_id, n)
        c = self._edge_index(data.start_boundary_b_id, n)
        if (b-c) % n not in (1, n-1):
            raise WorkPlanningValidationError('Die beiden Startgrenzen müssen benachbart sein.')
        corner_index = b if (b-c) % n == 1 else c
        corner = vertices[corner_index]
        forward, inverse = self._projector(vertices)
        polygon = transform(forward, Polygon(vertices))
        xy = [forward(*p) for p in vertices]
        ax, ay = xy[a]
        bx, by = xy[(a+1) % n]
        dx, dy = bx-ax, by-ay
        length = math.hypot(dx, dy)
        if length < 0.01:
            raise WorkPlanningValidationError('Ausrichtungskante ist zu kurz.')
        ux, uy = dx/length, dy/length
        nx, ny = -uy, ux
        center = polygon.representative_point()
        if (center.x-ax)*nx + (center.y-ay)*ny < 0: nx, ny = -nx, -ny
        widths = data.headland_working_widths or self.defaults(data).default_headland_working_widths
        margin = widths * working_width if data.headland_mode == 'all_around' else 0.0
        usable = polygon.buffer(-margin) if margin else polygon
        if usable.is_empty:
            raise WorkPlanningValidationError('Das Feld ist für die gewählte Vorgewendebreite zu klein.')
        # Parallelspuren im Abstand einer Arbeitsbreite; halbe Arbeitsbreite als Sicherheitsabstand.
        offsets = [((x-ax)*nx + (y-ay)*ny) for x,y in xy]
        start_offset = min(offsets) + working_width/2 + margin
        end_offset = max(offsets) - working_width/2 - margin
        if start_offset > end_offset:
            raise WorkPlanningValidationError('Keine reguläre Fahrspur innerhalb des Feldes möglich.')
        corner_xy = Point(*forward(*corner))
        candidates = []
        index = 0
        while start_offset + index * working_width <= end_offset + 1e-6:
            off = start_offset + index * working_width
            px, py = ax + nx*off, ay + ny*off
            line = LineString([(px-ux*100000,py-uy*100000),(px+ux*100000,py+uy*100000)])
            clipped = usable.intersection(line)
            segments = [clipped] if clipped.geom_type == 'LineString' else list(getattr(clipped, 'geoms', []))
            for segment in segments:
                if segment.geom_type != 'LineString' or segment.length < 0.1: continue
                for endpoint in (segment.coords[0],segment.coords[-1]):
                    point = Point(endpoint)
                    candidates.append((corner_xy.distance(point), endpoint))
            index += 1
            if index > 10000: raise WorkPlanningValidationError('Zu viele Fahrspuren.')
        if not candidates:
            raise WorkPlanningValidationError('Keine gültige reguläre Fahrspur gefunden.')
        _, best = min(candidates, key=lambda item: item[0])
        return list(inverse(*best))

    def preview(self, data):
        defaults = self.defaults(data)
        _, implement, field = self._data(data.tractor_id, data.implement_id, data.field_id)
        point = self._geometry(data, field, implement.working_width_m)
        return WorkPlanningPreview(**defaults.model_dump(),
            headland_working_widths=data.headland_working_widths or defaults.default_headland_working_widths,
            start_point=point,
            start_boundary_ids=[data.start_boundary_a_id, data.start_boundary_b_id])

    @staticmethod
    def _read(row):
        data = {column.name: getattr(row, column.name) for column in row.__table__.columns if column.name not in ('start_point_json','guidance_json')}
        data['start_point'] = json.loads(row.start_point_json)
        if data['created_at'].tzinfo is None:
            data['created_at'] = data['created_at'].replace(tzinfo=timezone.utc)
        return WorkPlanningRead.model_validate(data)

    def create(self, data):
        preview = self.preview(data)
        values = data.model_dump()
        values['headland_working_widths'] = preview.headland_working_widths
        values['start_point_json'] = json.dumps(preview.start_point)
        values['created_at'] = datetime.now(timezone.utc)
        row = WorkPlanning(**values)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._read(row)

    def list(self):
        return [self._read(row) for row in self.db.scalars(select(WorkPlanning).order_by(WorkPlanning.created_at.desc(),WorkPlanning.id.desc())).all()]

    def get(self, planning_id):
        row = self.db.get(WorkPlanning, planning_id)
        if row is None: raise WorkPlanningNotFoundError(f'Arbeitsplanung {planning_id} nicht gefunden.')
        return self._read(row)

    def delete(self, planning_id):
        row = self.db.get(WorkPlanning, planning_id)
        if row is None: raise WorkPlanningNotFoundError(f'Arbeitsplanung {planning_id} nicht gefunden.')
        self.db.delete(row)
        self.db.commit()

    def guidance(self, data):
        """Berechnet die komplette Spurplanung ohne Persistenz des Darstellungsmodus."""
        from pytrac_core.services.guidance.route_planner import Parameters, plan_route, GuidanceError
        tractor, implement, field = self._data(data.tractor_id, data.implement_id, data.field_id)
        vertices = self._edges(field)
        count = len(vertices)
        widths = data.headland_working_widths or self.calculate_headland_widths(
            tractor.length_m, implement.length_m, implement.working_width_m)
        try:
            return plan_route(Parameters(
                boundary=json.loads(field.boundary_json),
                alignment_edge=self._edge_index(data.alignment_boundary_id, count),
                start_edge_a=self._edge_index(data.start_boundary_a_id, count),
                start_edge_b=self._edge_index(data.start_boundary_b_id, count),
                working_width_m=implement.working_width_m,
                headland_passes=widths,
                headland_mode=data.headland_mode,
                turn_type=data.turn_type,
                bed_working=data.bed_working,
                wheelbase_m=tractor.wheelbase_m,
                max_steering_angle_deg=tractor.max_steering_angle_deg,
                output_mode=data.output_mode,
            ))
        except GuidanceError as exc:
            raise WorkPlanningValidationError(str(exc)) from exc

    def guidance_for_saved(self, planning_id, output_mode='turns'):
        """Neu berechnen aus den gespeicherten Planungsparametern."""
        from pytrac_core.api.schemas import GuidanceRequest
        plan = self.get(planning_id)
        return self.guidance(GuidanceRequest(**plan.model_dump(exclude={'id','start_point','created_at'}),
                                             output_mode=output_mode))
