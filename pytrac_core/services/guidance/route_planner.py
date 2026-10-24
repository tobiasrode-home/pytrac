"""Metrische Feldspurplanung mit optionalen, ungeprüften Wendemanövern.

Koordinaten extern: [Längengrad, Breitengrad] (WGS84).
Koordinaten intern: lokale azimutale Äquidistanzprojektion in Metern.
Wendemanöver werden NICHT auf Grenzverletzungen oder Hindernisse geprüft.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import transform, unary_union


class GuidanceError(ValueError):
    """Die Spurplanung ist für diese Eingaben nicht möglich."""


@dataclass(frozen=True)
class Parameters:
    boundary: list[list[float]]
    alignment_edge: int
    start_edge_a: int
    start_edge_b: int
    working_width_m: float
    headland_passes: int
    headland_mode: Literal["all_around", "headlands_only"]
    turn_type: Literal["u_turn", "y_turn"]
    bed_working: bool = False
    wheelbase_m: float = 3.0
    max_steering_angle_deg: float = 35.0
    output_mode: Literal["turns", "targets"] = "turns"
    implement_lead_m: float = 0.0
    headland_start_passes: int | None = None
    headland_end_passes: int | None = None
    implement_work_offset_m: float = 0.0
    guidance_mode: str = "straight"
    reference_edge_count: int = 1
    driven_reference: list[list[float]] | None = None


def _unit(v):
    length = math.hypot(*v)
    if length < 1e-9:
        raise GuidanceError("Ausrichtungskante hat keine Länge.")
    return v[0] / length, v[1] / length


def _segments(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    return [g for g in getattr(geometry, "geoms", ()) if g.geom_type == "LineString"]


def _headland_cut_halfplane(a, b, inward, clearance, extent):
    """Half-plane behind a real headland edge, offset into the field.

    Uses a large finite polygon in the local metric CRS. Unlike shortening
    a curve by its arclength, this makes all tracks end at the SAME physical
    headland boundary, even if the boundary is oblique.
    """
    u = _unit((b[0] - a[0], b[1] - a[1]))
    n = (-u[1], u[0])
    if n[0]*inward[0] + n[1]*inward[1] < 0:
        n = (-n[0], -n[1])
    x, y = a[0]+n[0]*clearance, a[1]+n[1]*clearance
    p = (x-u[0]*extent, y-u[1]*extent)
    q = (x+u[0]*extent, y+u[1]*extent)
    return Polygon([p, q,
        (q[0]+n[0]*extent, q[1]+n[1]*extent),
        (p[0]+n[0]*extent, p[1]+n[1]*extent)])


def _xy_line(a, b):
    return [[float(a[0]), float(a[1])], [float(b[0]), float(b[1])]]


def _sample_cubic(a, b, c, d, steps=18):
    points = []
    for k in range(steps + 1):
        t = k / steps
        s = 1 - t
        points.append([s**3*a[0]+3*s*s*t*b[0]+3*s*t*t*c[0]+t**3*d[0],
                       s**3*a[1]+3*s*s*t*b[1]+3*s*t*t*c[1]+t**3*d[1]])
    return points


def _turns(current, following, kind, radius):
    """Nur schematische Manöver; keine kinematisch exakte Fahrkurve.

    Ein U-Turn wird als glatter vorwärtsgerichteter Verbindungsbogen
    dargestellt; eine Y-Wendung besteht aus drei Teilzügen inklusive
    Rückwärtsfahrt. Diese Geometrien sind NICHT als Lenk-Solltrajektorien
    freigegeben.
    """
    a, b = current[-2], current[-1]
    c, d = following[0], following[1]
    ux, uy = _unit((b[0]-a[0], b[1]-a[1]))
    vx, vy = _unit((d[0]-c[0], d[1]-c[1]))
    reach = max(radius, 1.0)
    if kind == "u_turn":
        curve = _sample_cubic(b, [b[0]+ux*reach,b[1]+uy*reach],
                              [c[0]-vx*reach,c[1]-vy*reach], c)
        return [{"gear":"forward", "coordinates_m":curve}]
    # Schematisches dreizügiges Y: vorwärts, rückwärts, vorwärts.
    mid = [(b[0]+c[0])/2, (b[1]+c[1])/2]
    tip = [mid[0]+ux*reach,mid[1]+uy*reach]
    reverse_end = [mid[0]-ux*reach*0.6,mid[1]-uy*reach*0.6]
    return [{"gear":"forward","coordinates_m":_xy_line(b,tip)},
            {"gear":"reverse","coordinates_m":_xy_line(tip,reverse_end)},
            {"gear":"forward","coordinates_m":_xy_line(reverse_end,c)}]



def _headland_tracks(polygon, xy, width, passes, mode, selected_edges, wgs):
    """Gerade Randbahnen, seitenweise. Keine Übergangs- oder Rangiertrajektorien.

    Der letzte (äußere) Streifen wird immer an die echte Feldkante
    angelegt; Restbreite wird ausschließlich zur vorletzten Bahn überlappt.
    """
    result = []
    count = len(xy)
    from shapely.geometry import box
    for edge_id in range(count):
        a = xy[edge_id]
        b = xy[(edge_id + 1) % count]
        u = _unit((b[0]-a[0], b[1]-a[1]))
        n = (-u[1], u[0])
        probe = min(.1, width*.01)
        middle = ((a[0]+b[0])/2, (a[1]+b[1])/2)
        if not polygon.covers(Point(middle[0]+n[0]*probe,middle[1]+n[1]*probe)):
            n = (-n[0],-n[1])
        if mode == 'headlands_only' and edge_id not in selected_edges:
            continue
        side_passes = selected_edges.get(edge_id, passes) if mode == 'headlands_only' else passes
        band_width = side_passes * width
        # Feldseiten-Ecken werden durch Projektion auf die endliche
        # Originalkante begrenzt; dies erzeugt bewusst keine Konturkurven.
        # Für nicht-rechteckige Ecken kann ein unbearbeiteter Keil entstehen.
        centers = [width*(k+.5) for k in range(side_passes)]
        centers[-1] = band_width-width/2 if side_passes>1 else width/2
        # Bandbreite ist eine ganzzahlige Anzahl Arbeitsbreiten, daher
        # reguläre Bahnen ohne erzwungene Überlappung.
        for k, distance in enumerate(reversed(centers)):
            o = (a[0]+n[0]*distance, a[1]+n[1]*distance)
            line = LineString([(o[0]-u[0]*100000,o[1]-u[1]*100000),
                               (o[0]+u[0]*100000,o[1]+u[1]*100000)])
            for segment in _segments(polygon.intersection(line)):
                # Beschränkung auf die Projektion der tatsächlichen Feldseite.
                lo = max(0., min((q[0]-a[0])*u[0]+(q[1]-a[1])*u[1] for q in (segment.coords[0],segment.coords[-1])))
                hi = min(math.dist(a,b), max((q[0]-a[0])*u[0]+(q[1]-a[1])*u[1] for q in (segment.coords[0],segment.coords[-1])))
                if hi-lo < max(.25,width*.2):continue
                p0=[o[0]+u[0]*lo,o[1]+u[1]*lo]
                p1=[o[0]+u[0]*hi,o[1]+u[1]*hi]
                result.append({'side_id':edge_id,'pass_index':k+1,
                               'length_m':round(hi-lo,2),
                               'coordinates':[wgs(p0),wgs(p1)],
                               'points_m':[p0,p1]})
    return result


def plan_route(params: Parameters) -> dict:
    if not math.isfinite(params.implement_lead_m) or params.implement_lead_m < 0:
        raise GuidanceError("Geräte-Vorlauf muss eine endliche, nichtnegative Meterzahl sein.")
    if not math.isfinite(params.implement_work_offset_m):
        raise GuidanceError("Geräte-Arbeitspunktversatz muss endlich sein.")
    if any(v is not None and not 1 <= v <= 100 for v in (params.headland_start_passes, params.headland_end_passes)):
        raise GuidanceError("Stirnseiten-Vorgewende muss 1 bis 100 Arbeitsbreiten betragen.")

    if params.working_width_m <= 0 or not math.isfinite(params.working_width_m):
        raise GuidanceError("Arbeitsbreite muss positiv und endlich sein.")
    if not 1 <= params.headland_passes <= 100:
        raise GuidanceError("Vorgewende muss zwischen 1 und 100 Arbeitsbreiten liegen.")
    if params.bed_working and params.turn_type != "u_turn":
        raise GuidanceError("Beetbearbeitung ist nur bei U-Turn zulässig.")
    if not params.wheelbase_m > 0 or not 0 < params.max_steering_angle_deg < 90:
        raise GuidanceError("Radstand oder Lenkwinkel ungültig.")
    vertices = params.boundary[:-1]
    if len(vertices) < 3 or params.boundary[0] != params.boundary[-1]:
        raise GuidanceError("Feldgrenze muss geschlossen sein.")
    polygon_ll = Polygon(vertices)
    if not polygon_ll.is_valid or polygon_ll.area <= 0:
        raise GuidanceError("Feldpolygon ist ungültig.")
    n = len(vertices)
    if any(not 0 <= i < n for i in (params.alignment_edge,params.start_edge_a,params.start_edge_b)):
        raise GuidanceError("Ungültige Kanten-ID.")
    if (params.start_edge_a-params.start_edge_b) % n not in (1,n-1):
        raise GuidanceError("Startgrenzen müssen benachbart sein.")
    corner_index = (params.start_edge_a if (params.start_edge_a-params.start_edge_b)%n == 1
                    else params.start_edge_b)
    center_lon = sum(p[0] for p in vertices)/n
    center_lat = sum(p[1] for p in vertices)/n
    crs = CRS.from_proj4(f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +datum=WGS84 +units=m +no_defs")
    forward = Transformer.from_crs("EPSG:4326",crs,always_xy=True).transform
    inverse = Transformer.from_crs(crs,"EPSG:4326",always_xy=True).transform
    polygon = transform(forward,polygon_ll)
    xy = [forward(*p) for p in vertices]
    origin = xy[params.alignment_edge]
    edge_end = xy[(params.alignment_edge+1)%n]
    u = _unit((edge_end[0]-origin[0],edge_end[1]-origin[1]))
    normal = (-u[1],u[0])
    # Die Referenzkante ist die Null-Linie für die Spurabstände.
    # Bestimme die Feldinnenseite anhand der Polygonorientierung und
    # verifiziere sie nahe der Kantenmitte. Der Schwerpunkt ist dafür
    # bei konkaven Feldern nicht zuverlässig.
    signed_area = sum(xy[j][0] * xy[(j+1) % n][1] -
                      xy[(j+1) % n][0] * xy[j][1] for j in range(n))
    if signed_area < 0:
        normal = (-normal[0], -normal[1])
    midpoint = ((origin[0] + edge_end[0]) / 2,
                (origin[1] + edge_end[1]) / 2)
    probe = min(0.1, params.working_width_m * 0.01)
    if not polygon.covers(Point(midpoint[0] + normal[0] * probe,
                                midpoint[1] + normal[1] * probe)):
        raise GuidanceError("Referenzkante hat keine eindeutige Feldinnenseite.")
    width = params.working_width_m
    margin = params.headland_passes*width
    start_margin = (params.headland_start_passes or params.headland_passes)*width
    end_margin = (params.headland_end_passes or params.headland_passes)*width

    # Bei "nur Stirnseiten" ist ein globaler Korridor entlang der
    # Fahrtrichtung falsch: an schrägen Stirnseiten entstehen sonst
    # unterschiedliche, teilweise zu kurze Vorgewendeabstände.
    # Stattdessen wird JEDE geschnittene Fahrspur an BEIDEN Enden um
    # die gewählte Vorgewendebreite gekürzt.
    # Der halbe Arbeitsbreitenabstand schützt die seitlichen Ränder
    # vor einer Arbeitsgeräte-Überdeckung außerhalb des Polygons.
    if params.headland_mode == "all_around":
        usable = polygon.buffer(-margin, join_style=2)
    else:
        usable = polygon.buffer(-width / 2, join_style=2)
    if usable.is_empty:
        raise GuidanceError("Keine Fläche innerhalb des Vorgewendes vorhanden.")
    offsets=[((x-origin[0])*normal[0]+(y-origin[1])*normal[1]) for x,y in xy]
    max_offset=max(offsets)
    # Zentren der Arbeitsstreifen liegen mindestens eine halbe
    # Arbeitsbreite innerhalb der äußeren Feldgrenzen.
    # Der Ursprung liegt EXAKT auf der ausgewählten Referenzkante.
    # Die erste Spurachse wird von dort um eine halbe Arbeitsbreite
    # nach innen verschoben; weitere Achsen folgen im Raster width.
    # Ein negativer Offset ist nur bei konkaven Feldpolygonen möglich,
    # wo andere Teile des Feldes hinter der verlängerten Referenzlinie
    # liegen. Solche Teile können mit diesem Referenzraster nicht
    # vollständig abgedeckt werden und werden nicht als neue
    # Startkante interpretiert.
    start=width/2
    stop=max_offset-width/2
    if stop < start:
        raise GuidanceError("Feld zu schmal für die Fahrspuren.")
    strips=[]
    if params.guidance_mode == "boundary_reference":
        if not 1 <= params.reference_edge_count < n:
            raise GuidanceError("Anzahl Referenzkanten ungültig.")
        # Ausgewählte Kanten müssen in Polygonreihenfolge aufeinanderfolgen.
        # Die Feldgrenze ist die äußere Null-Linie, die erste befahrbare
        # Referenzspur liegt eine halbe Arbeitsbreite im Feld.
        ids=[(params.alignment_edge+j)%n for j in range(params.reference_edge_count+1)]
        chain=LineString([xy[j] for j in ids])
        if params.driven_reference:
            driven=LineString([forward(*point) for point in params.driven_reference])
            if not driven.is_simple or driven.length < width:
                raise GuidanceError("Aufgezeichnete Referenzfahrt ist ungeeignet.")
            base=driven
            first_distance=0.0
        else:
            base=chain
            first_distance=width/2
        # Polygonorientierung: bei CCW liegt das Innere links der Kanten.
        side="left" if signed_area>0 else "right"
        if params.driven_reference:
            ca,cb=chain.coords[0],chain.coords[-1]
            da,db=base.coords[0],base.coords[-1]
            if (cb[0]-ca[0])*(db[0]-da[0])+(cb[1]-ca[1])*(db[1]-da[1])<0:
                side="right" if side=="left" else "left"
        max_dist=polygon.bounds[2]-polygon.bounds[0]+polygon.bounds[3]-polygon.bounds[1]
        # The preceding and following polygon edges are the two actual
        # headland boundaries for a chain of consecutive reference edges.
        # Clip the tracks to parallel lines set one headland width INSIDE
        # those edges, instead of removing an arbitrary arclength.
        # For boundary-derived offsets, clipping against polygon.buffer(-5m)
        # can truncate a curved outermost line at a bend. The offset itself
        # already provides the 5m clearance from the chosen reference edge.
        reference_usable=polygon if not params.driven_reference else usable
        if params.headland_mode == "headlands_only" and not params.driven_reference:
            before=(params.alignment_edge-1)%n
            after=(params.alignment_edge+params.reference_edge_count)%n
            # For a valid simple polygon, the polygon interior is on the
            # left for CCW and on the right for CW winding.
            extent=max(1000.,max_dist*20)
            for edge_id,clearance in ((before,start_margin),(after,end_margin)):
                a,b=xy[edge_id],xy[(edge_id+1)%n]
                direction=_unit((b[0]-a[0],b[1]-a[1]))
                inward=(-direction[1],direction[0])
                if signed_area<0:inward=(-inward[0],-inward[1])
                reference_usable=reference_usable.intersection(
                    _headland_cut_halfplane(a,b,inward,clearance,extent))
        for i in range(min(2000,int(max_dist/width)+2)):
            distance=first_distance+i*width
            # Avoid exact coincidence with the lateral buffer boundary;
            # the 1 cm numerical tolerance is used for the FIRST track only.
            if i == 0 and not params.driven_reference:
                distance += 0.01
            try:
                curve=base.parallel_offset(distance,side,join_style=2)
            except Exception as exc:
                raise GuidanceError("Referenzkante kann nicht versetzt werden.") from exc
            # Fertige Offset-Linie an ihren Enden geradlinig bis zu den
            # tatsächlichen Stirnseiten verlängern. Die innere Geometrie
            # und alle Knicke bleiben unverändert; anschließend begrenzt
            # reference_usable die Spur am Vorgewende.
            if not params.driven_reference and curve.geom_type == "LineString":
                pts=list(curve.coords)
                if len(pts)>=2:
                    reach=max(30.,max_dist)
                    a,b=pts[0],pts[1]
                    c,d=pts[-2],pts[-1]
                    ua=_unit((b[0]-a[0],b[1]-a[1]))
                    ub=_unit((d[0]-c[0],d[1]-c[1]))
                    curve=LineString([(a[0]-ua[0]*reach,a[1]-ua[1]*reach),
                                      *pts,
                                      (d[0]+ub[0]*reach,d[1]+ub[1]*reach)])
            # Die Spurmitte muss mindestens eine halbe Arbeitsbreite
            # Abstand zu ALLEN seitlichen Feldgrenzen haben. Die
            # Stirnseiten werden weiterhin separat durch die
            # Vorgewende-Halbebenen begrenzt.
            # Nur die gegenüberliegende (linke) Feldseite als
            # Sicherheitsabstand anwenden. Ein globaler Innenpuffer
            # würde die rechte Referenzspur am Knick erneut abschneiden.
            opposite=(params.alignment_edge+params.reference_edge_count+1)%n
            # Gegenüberliegende Seitenkette: alle Kanten außer der
            # Referenzkette und den beiden Stirnseiten.
            excluded={(params.alignment_edge+j)%n for j in range(params.reference_edge_count)}
            excluded.add((params.alignment_edge-1)%n)
            excluded.add((params.alignment_edge+params.reference_edge_count)%n)
            forbidden=unary_union([
                LineString([xy[j],xy[(j+1)%n]]).buffer(width/2-0.01)
                for j in range(n) if j not in excluded])
            safe_area=reference_usable.difference(forbidden)
            segments=_segments(curve.intersection(safe_area))
            found=False
            for segment in segments:
                if segment.length < max(width,2):continue
                # Stirnseiten wie bisher um die festgelegten Vorwendebreiten
                # kürzen, gemessen entlang der jeweiligen Kurvenspur.
                if segment.length < max(width,2):continue
                found=True
                coords=[list(pt) for pt in segment.coords]
                strips.append({"offset":i,"length_m":round(segment.length,2),"points_m":coords})
            if i>2 and not found:
                break
        # V39: Zusätzliche linke Randspur nur dann, wenn die bestehenden
        # 10-m-Arbeitsbänder dort eine nennenswerte Restfläche lassen.
        # Eine Überlappung mit der bisherigen letzten Spur ist erlaubt.
        # Die linke Randspur wird aus der echten gegenüberliegenden
        # Feldgrenze konstruiert, nicht durch Verschieben der rechten Spur.
        if not params.driven_reference and params.headland_mode == "headlands_only":
            opposite_ids=[
                j for j in range(n)
                if j not in excluded
            ]
            if opposite_ids and strips:
                opposite_edges=[LineString([xy[j],xy[(j+1)%n]]) for j in opposite_ids]
                from shapely.ops import linemerge
                from shapely.geometry import MultiLineString
                left_boundary=linemerge(MultiLineString(opposite_edges))
                if left_boundary.geom_type == "LineString":
                    # Polygon-Kanten sind gleich orientiert. Die Innenseite
                    # entspricht daher der Seite der ursprünglichen Kette.
                    try:
                        left_candidate=left_boundary.parallel_offset(
                            width/2,side,join_style=2)
                    except Exception:
                        left_candidate=None
                    if left_candidate is not None and not left_candidate.is_empty:
                        # Vorgewende-Halbebenen gelten auch für diese Spur.
                        # Zusätzlich 5 m Sicherheitsabstand zur gesamten
                        # linken Grenzkette einhalten (numerische Toleranz).
                        allowed=reference_usable.difference(
                            left_boundary.buffer(width/2-0.01))
                        # Die Randspur muss eine zusammenhängende, sinnvolle
                        # Fahrstrecke sein; keine isolierten Mini-Segmente.
                        candidates=sorted(
                            _segments(left_candidate.intersection(allowed)),
                            key=lambda g:g.length,reverse=True)
                        if candidates:
                            candidate=candidates[0]
                            if candidate.length >= max(20.,width*3):
                                covered=unary_union([
                                    LineString(t["points_m"]).buffer(
                                        width/2,cap_style=2,join_style=2)
                                    for t in strips])
                                # Nur zusätzliche Abdeckung innerhalb des
                                # nutzbaren Feldes zählt.
                                new_band=candidate.buffer(
                                    width/2,cap_style=2,join_style=2
                                ).intersection(reference_usable)
                                gain=new_band.difference(covered).area
                                if gain >= width*width*.15:
                                    strips.append({
                                        "offset":max(t["offset"] for t in strips)+1,
                                        "length_m":round(candidate.length,2),
                                        "points_m":[list(p) for p in candidate.coords]})
    else:
        strips=[]
        for i in range(min(10000,int((stop-start)/width+1e-8)+1)):
            offset=start+i*width
            px=origin[0]+normal[0]*offset
            py=origin[1]+normal[1]*offset
            line=LineString([(px-u[0]*100000,py-u[1]*100000),(px+u[0]*100000,py+u[1]*100000)])
            for segment in _segments(usable.intersection(line)):
                if segment.length < max(0.25,width*0.2):
                    continue
                a,b=segment.coords[0],segment.coords[-1]
                if (b[0]-a[0])*u[0]+(b[1]-a[1])*u[1]<0:
                    a,b=b,a
                if params.headland_mode == "headlands_only":
                    # Abstand an der tatsächlichen, lokalen Stirnseite
                    # der jeweiligen Spur, nicht am globalen Feld-Extremum.
                    # Der seitliche Innenpuffer ist für die Spurmitte
                    # erforderlich und bleibt unverändert.
                    length=math.dist(a,b)
                    # Anfang/Ende beziehen sich auf die Referenzkanten-Richtung u,
                    # nicht auf die wechselnde Fahrtrichtung der einzelnen Spur.
                    if length <= start_margin+end_margin+max(0.25,width*0.2):
                        continue
                    a=(a[0]+u[0]*start_margin,a[1]+u[1]*start_margin)
                    b=(b[0]-u[0]*end_margin,b[1]-u[1]*end_margin)
                length=math.dist(a,b)
                if length < max(0.25,width*0.2):
                    continue
                strips.append({"offset":i,"length_m":round(length,2),"points_m":_xy_line(a,b)})
    if not strips:
        raise GuidanceError("Keine regulären Fahrspuren innerhalb des Feldes.")
    corner=Point(xy[corner_index])
    # Wähle die Spur, deren Endpunkt dem gewählten Starteck am nächsten liegt.
    first=(min(strips,key=lambda s:s["offset"]) if params.guidance_mode=="boundary_reference" else min(strips,key=lambda s:min(corner.distance(Point(s['points_m'][0])),corner.distance(Point(s['points_m'][-1])))))
    reverse_first=corner.distance(Point(first['points_m'][-1])) < corner.distance(Point(first['points_m'][0]))
    # Beetbearbeitung: alternierend jede zweite Spur, danach die ausgelassenen.
    by_offset=sorted(strips,key=lambda s:(s['offset'],s['points_m'][0]))
    if params.bed_working:
        by_offset=by_offset[::2]+by_offset[1::2]
    else:
        # Start am ausgewählten Eck, danach räumlich benachbarte Streifen.
        by_offset=sorted(strips,key=lambda s:abs(s['offset']-first['offset']))
    by_offset.remove(first)
    ordered=[first]+by_offset
    if reverse_first: ordered[0]['points_m'].reverse()
    for i in range(1,len(ordered)):
        prev=ordered[i-1]['points_m'][-1]
        a,b=ordered[i]['points_m'][0],ordered[i]['points_m'][-1]
        if math.dist(prev,b)<math.dist(prev,a): ordered[i]['points_m'].reverse()
    def wgs(point):
        lon,lat=inverse(*point)
        return [round(lon,8),round(lat,8)]
    tracks=[]
    for i,strip in enumerate(ordered):
        tracks.append({"id":i+1,"type":"work","offset_index":strip['offset'],
                       "length_m":strip['length_m'],
                       "coordinates":[wgs(p) for p in strip['points_m']]})
    # V8: Vorgewende ist eine separate Phase nach dem Hauptfeld.
    # Die Stirnseiten werden anhand der Kantennormalen und der
    # Ausrichtung der Hauptspuren ermittelt.
    side_candidates=[]
    for j in range(n):
        ea,eb=xy[j],xy[(j+1)%n]
        v=_unit((eb[0]-ea[0],eb[1]-ea[1]))
        signed=( (ea[0]+eb[0])/2-origin[0])*u[0]+((ea[1]+eb[1])/2-origin[1])*u[1]
        side_candidates.append((j,abs(v[0]*u[0]+v[1]*u[1]),signed))
    # Kanten quer zur Hauptspur: je ein Extrem in +/- Fahrtrichtung.
    negative=min(side_candidates,key=lambda q:q[2])
    positive=max(side_candidates,key=lambda q:q[2])
    selected={negative[0]:params.headland_start_passes or params.headland_passes,
              positive[0]:params.headland_end_passes or params.headland_passes}
    headland_tracks=_headland_tracks(polygon,xy,width,params.headland_passes,
                                    params.headland_mode,selected,wgs)
    for k,t in enumerate(headland_tracks):
        t['id']=k+1
        t['type']='headland_work'
    headland_events=[]
    for t in headland_tracks:
        a,b=t['points_m']
        ux,uy=_unit((b[0]-a[0],b[1]-a[1]))
        for action,pt in (('lower',a),('raise',b)):
            stop=[pt[0]+ux*params.implement_work_offset_m,
                  pt[1]+uy*params.implement_work_offset_m]
            headland_events.append({'track_id':t['id'],'side_id':t['side_id'],
                'phase':'headland','action':action,
                'label':'Arbeitsgerät absenken' if action=='lower' else 'Arbeitsgerät ausheben',
                'coordinate':wgs(stop),'vehicle_stop_coordinate':wgs(stop),
                'work_boundary':wgs(pt),'requires_stop':True,
                'requires_driver_confirmation':True})
    for t in headland_tracks:t.pop('points_m')
    # Gerätebefehle: Der exakte Arbeitspunkt liegt jeweils an den beiden
    # Endpunkten der gekürzten Hauptfeldspur. Vorwarnungen sind optional.
    # Für den Vorlauf wird die Spurachse verlängert; diese Punkte sind
    # Hinweispositionen und KEINE geprüften, befahrbaren Routenpunkte.
    implement_events=[]
    for i, strip in enumerate(ordered):
        a,b=strip['points_m'][0],strip['points_m'][-1]
        ux,uy=_unit((b[0]-a[0],b[1]-a[1]))
        length=math.dist(a,b)
        for action, position, direction in (("lower",a,-1),("raise",b,-1)):
            # work_offset_m: positiv = Arbeitspunkt liegt hinter dem
            # Fahrzeug-Referenzpunkt in Fahrtrichtung. GPS-Stopppunkt
            # ist deshalb vor der Arbeitsgrenze; negativ entsprechend dahinter.
            stop=[position[0]+ux*params.implement_work_offset_m,
                  position[1]+uy*params.implement_work_offset_m]

            event={"track_id":i+1,"action":action,
                   "label":"Arbeitsgerät absenken" if action=="lower" else "Arbeitsgerät ausheben",
                   "work_boundary":wgs(position),"coordinate":wgs(stop),
                   "vehicle_stop_coordinate":wgs(stop),
                   "implement_work_offset_m":params.implement_work_offset_m,
                   "requires_stop":True,"requires_driver_confirmation":True,
                   "reference":"Hauptfeld/Vorgewende", "lead_m":params.implement_lead_m}
            if params.implement_lead_m:
                # Vor Beginn: vor der Spur. Vor Ende: innerhalb der Spur.
                # Nur bei langen Spuren sinnvoll; Warnpunkt sonst entfällt.
                if action=="lower":
                    warning=[stop[0]-ux*params.implement_lead_m,stop[1]-uy*params.implement_lead_m]
                elif params.implement_lead_m < length:
                    warning=[stop[0]-ux*params.implement_lead_m,stop[1]-uy*params.implement_lead_m]
                else:
                    warning=None
                if warning is not None:
                    event['advance_warning']=wgs(warning)
            implement_events.append(event)
    radius=params.wheelbase_m/math.tan(math.radians(params.max_steering_angle_deg))
    transitions=[]
    for i in range(len(ordered)-1):
        current=ordered[i]['points_m'];following=ordered[i+1]['points_m']
        entry=wgs(following[0])
        item={"from_track":i+1,"to_track":i+2,"target":entry,
              "mode":params.output_mode,"segments":[]}
        if params.output_mode == "turns":
            item['segments']=[{"gear":segment['gear'],
                               "coordinates":[wgs(p) for p in segment['coordinates_m']]}
                              for segment in _turns(current,following,params.turn_type,radius)]
        transitions.append(item)
    return {"guidance_mode":params.guidance_mode,"reference_edge_count":params.reference_edge_count,"reference_source":("driven" if params.driven_reference else "boundary"),"headland_tracks":headland_tracks,"headland_implement_events":headland_events,
            "headland_track_count":len(headland_tracks),"headland_navigation":"straight_tracks_only_manual_repositioning",
            "implement_events":implement_events,"implement_lead_m":params.implement_lead_m,
            "implement_control":"manual_driver_instruction",
            "start_point":tracks[0]['coordinates'][0],"tracks":tracks,
            "transitions":transitions,"track_count":len(tracks),
            "work_length_m":round(sum(t['length_m'] for t in tracks),2),
            "minimum_turning_radius_m":round(radius,2),
            "headland_width_m":round(margin,2),
            "headland_start_width_m":round(start_margin,2),
            "headland_end_width_m":round(end_margin,2),

            "output_mode":params.output_mode,
            "turns_collision_checked":False,
            "turns_kinematically_validated":False,
            "warnings":(["Vorgewende: nur gerade Spuren, Umsetzen und Rückwärtsfahrt erfolgen eigenverantwortlich. Eckbereiche bei schrägen Feldseiten auf Restflächen prüfen.", "Wendekurven sind nur schematische Vorschläge: keine Grenz-, Hindernis- oder Kinematikprüfung. Nicht zur automatischen Lenkung verwenden."]
                        if params.output_mode == "turns" else
                        ["Vorgewende: nur gerade Spuren, Umsetzen und Rückwärtsfahrt erfolgen eigenverantwortlich. Eckbereiche bei schrägen Feldseiten auf Restflächen prüfen.", "Zielpunkte sind Navigationshilfen; die Verbindung zwischen den Spuren ist nicht geprüft."])}


def manual_track_guidance(result, lines, implement_offset_m=0.0, lead_m=0.0):
    '''V40: Nutzer-Spuren statt automatischer Hauptfeldspuren; keine erfundenen Wendekurven.'''
    from pyproj import Geod
    import copy
    geod=Geod(ellps='WGS84')
    result=copy.deepcopy(result)
    tracks=[]
    events=[]
    for idx, coords in enumerate(lines,1):
        length=sum(geod.inv(a[0],a[1],b[0],b[1])[2] for a,b in zip(coords,coords[1:]))
        tracks.append({'id':idx,'coordinates':coords,'length_m':round(length,2),'type':'main_work'})
        for action,position,next_point in (('lower',coords[0],coords[1]),('raise',coords[-1],coords[-2])):
            # Der letzte Tangentenvektor zeigt wie der erste in Fahrtrichtung.
            if action=='lower':
                azimuth=geod.inv(*position,*next_point)[0]
            else:
                azimuth=geod.inv(*next_point,*position)[0]
            lon,lat,_=geod.fwd(*position,azimuth,implement_offset_m)
            event={'track_id':idx,'action':action,'label':'Arbeitsgerät absenken' if action=='lower' else 'Arbeitsgerät ausheben',
                   'work_boundary':position,'coordinate':[lon,lat],'vehicle_stop_coordinate':[lon,lat],
                   'implement_work_offset_m':implement_offset_m,'requires_stop':True,
                   'requires_driver_confirmation':True,'reference':'Hauptfeld/Vorgewende','lead_m':lead_m}
            if lead_m and (action=='lower' or lead_m<length):
                wlon,wlat,_=geod.fwd(lon,lat,azimuth,-lead_m)
                event['advance_warning']=[wlon,wlat]
            events.append(event)
    result['headland_tracks']=[]
    result['headland_implement_events']=[]
    result['headland_track_count']=0
    result['headland_navigation']='manual'
    result['guidance_mode']='manual'
    result['implement_control']='manual_driver_instruction'
    result['tracks']=tracks
    result['track_count']=len(tracks)
    result['work_length_m']=round(sum(t['length_m'] for t in tracks),2)
    result['start_point']=tracks[0]['coordinates'][0]
    result['implement_events']=events
    result['transitions']=[{'from_track':i,'to_track':i+1,'target':tracks[i]['coordinates'][0],
                            'mode':'targets','segments':[]} for i in range(1,len(tracks))]
    result['reference_source']='manual'
    result['output_mode']='targets'
    result['turns_collision_checked']=False
    result['turns_kinematically_validated']=False
    result['warnings']=list(result.get('warnings',[]))+['Manuelle Spuren: Wendemanöver nicht berechnet. Geräteaktionen müssen bestätigt werden.']
    return result
