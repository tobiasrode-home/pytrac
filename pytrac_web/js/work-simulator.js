"use strict";

/*
 * PyTrac – Arbeitsgang-Simulator
 *
 * - Auswahl von Feld, Traktor und Anbaugerät
 * - Automatische Berechnung des Vorgewendes
 * - AB-Spuren mit einstellbarem Spurabstand
 * - Synthetische GPS-Daten
 * - Start, Pause, Fortsetzen und Zurücksetzen
 *
 * Wendekreis-Durchmesser: 12 m (fester Simulationswert)
 * Die Wendekurven sind geometrische Näherungen.
 */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const EARTH_RADIUS = 6378137;
  const TURN_DIAMETER_M = 12;
  const TURN_RADIUS_M = TURN_DIAMETER_M / 2;
  const GPS_STEP_M = 2;
  const ANIMATION_INTERVAL_MS = 35;
  const EPSILON = 1e-8;

  let fields = [];
  let tractors = [];
  let implementsList = [];

  let map = null;
  let layerGroup = null;
  let timer = null;

  let route = [];
  let routeIndex = 0;
  let running = false;
  let paused = false;
  let finished = false;
  let animationToken = 0;

  let drivenDistanceM = 0;
  let lastPoint = null;
  let currentMarker = null;
  let activeProjection = null;

  // ----------------------------------------------------------
  // Hilfsfunktionen
  // ----------------------------------------------------------

  function rad(deg) {
    return deg * Math.PI / 180;
  }

  function deg(value) {
    return value * 180 / Math.PI;
  }

  function distance(a, b) {
    return Math.hypot(b.x - a.x, b.y - a.y);
  }

  function vector(x, y) {
    return { x, y };
  }

  function add(a, b) {
    return vector(a.x + b.x, a.y + b.y);
  }

  function subtract(a, b) {
    return vector(a.x - b.x, a.y - b.y);
  }

  function scale(a, factor) {
    return vector(a.x * factor, a.y * factor);
  }

  function normalize(a) {
    const length = Math.hypot(a.x, a.y);
    return length < EPSILON
      ? vector(0, 0)
      : vector(a.x / length, a.y / length);
  }

  function message(text, isError = false) {
    const element = $("sim-message");
    if (!element) return;

    element.textContent = text;
    element.classList.toggle("error", isError);
  }

  function status(text) {
    const element = $("sim-status");
    if (element) element.textContent = text;
  }

  function setText(id, value) {
    const element = $(id);
    if (element) element.textContent = value;
  }

  function formatNumber(value, digits = 1) {
    return Number(value).toLocaleString("de-DE", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    });
  }

  function readNumber(id, min, max) {
    const element = $(id);
    const value = Number(element?.value);

    if (
      !element ||
      element.value.trim() === "" ||
      !Number.isFinite(value) ||
      value < min ||
      value > max
    ) {
      throw new Error(
        `${id}: Bitte einen Wert zwischen ${min} und ${max} eingeben.`
      );
    }

    return value;
  }

  async function apiGet(path) {
    if (typeof window.request !== "function") {
      throw new Error(
        "Die Funktion window.request() fehlt. " +
        "Bitte app.js vorher laden."
      );
    }

    return window.request(path);
  }

  function positiveValue(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0
      ? number
      : null;
  }

  // ----------------------------------------------------------
  // Zusätzliche Steuerelemente
  // ----------------------------------------------------------

  function ensureExtraControls() {
    const grid = $("sim-field")?.closest(".form-grid");

    if (!grid) {
      throw new Error(
        "Der Simulationsbereich mit .form-grid wurde nicht gefunden."
      );
    }

    function addSelect(id, labelText) {
      if ($(id)) return;

      const label = document.createElement("label");
      label.textContent = labelText;

      const select = document.createElement("select");
      select.id = id;
      select.required = true;

      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Bitte auswählen";

      select.appendChild(option);
      label.appendChild(select);
      grid.insertBefore(label, grid.firstChild);
    }

    function addInput(id, labelText, value, min, max, step) {
      if ($(id)) return;

      const label = document.createElement("label");
      label.textContent = labelText;

      const input = document.createElement("input");
      input.id = id;
      input.type = "number";
      input.min = String(min);
      input.max = String(max);
      input.step = String(step);
      input.value = String(value);
      input.required = true;

      label.appendChild(input);
      grid.appendChild(label);
    }

    addSelect("sim-tractor", "Traktor");

    addInput(
      "sim-spacing",
      "Spurabstand (m)",
      6,
      0.5,
      60,
      0.1
    );

    if (!$("sim-headland-info")) {
      const info = document.createElement("p");
      info.id = "sim-headland-info";
      info.className = "muted";
      info.setAttribute("role", "status");

      const reference = $("sim-reference-info");

      if (reference?.parentNode) {
        reference.parentNode.insertBefore(info, reference);
      } else {
        grid.parentNode.appendChild(info);
      }
    }
  }

  // ----------------------------------------------------------
  // Maschinen- und Feldauswahl
  // ----------------------------------------------------------

  function fillSelect(id, items, labelFn) {
    const select = $(id);
    if (!select) return;

    const previous = select.value;
    select.replaceChildren();

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Bitte auswählen";
    select.appendChild(placeholder);

    for (const item of items) {
      const option = document.createElement("option");
      option.value = String(item.id);
      option.textContent = labelFn(item);
      select.appendChild(option);
    }

    if (items.some((item) => String(item.id) === previous)) {
      select.value = previous;
    }
  }

  function selectedField() {
    return fields.find(
      (item) => String(item.id) === $("sim-field")?.value
    );
  }

  function selectedTractor() {
    return tractors.find(
      (item) => String(item.id) === $("sim-tractor")?.value
    );
  }

  function selectedImplement() {
    return implementsList.find(
      (item) => String(item.id) === $("sim-implement")?.value
    );
  }

  /*
   * Vorgewende:
   * - Gespannlänge wird aus den gespeicherten Maschinenwerten
   *   näherungsweise berechnet.
   * - Die Länge wird auf ein Vielfaches der Arbeitsbreite
   *   aufgerundet.
   * - Der feste Wendekreis wird zusätzlich berücksichtigt.
   *
   * Beispiel:
   * Arbeitsbreite 2 m, Gespann 6 m -> Vorgewende 6 m.
   * Arbeitsbreite 2 m, Gespann 7 m -> Vorgewende 8 m.
   */
  function getRigGeometry() {
    const tractor = selectedTractor();
    const implement = selectedImplement();

    if (!tractor || !implement) {
      throw new Error(
        "Bitte einen Traktor und ein Anbaugerät auswählen."
      );
    }

    const tractorLength = positiveValue(tractor.length_m);
    const implementLength = positiveValue(implement.length_m);
    const width = positiveValue(implement.working_width_m);

    if (!tractorLength || !implementLength || !width) {
      throw new Error(
        "Traktorlänge, Gerätelänge oder Arbeitsbreite fehlen " +
        "in den gespeicherten Maschinendaten."
      );
    }

    const hitch = Number(implement.hitch_offset_m || 0);
    const edge = Number(implement.working_edge_offset_m || 0);
    const margin = Math.max(
      0,
      Number(implement.headland_margin_m || 0)
    );

    let rigLength;

    if (implement.mount_position === "front") {
      rigLength = Math.max(
        tractorLength,
        tractorLength / 2 + implementLength
      );
    } else {
      rigLength =
        tractorLength +
        implementLength +
        Math.abs(hitch) +
        Math.abs(edge);
    }

    const roundedLength =
      Math.ceil((rigLength - EPSILON) / width) * width;

    const headland = Math.max(
      roundedLength,
      TURN_RADIUS_M,
      margin
    );

    return {
      tractor,
      implement,
      width,
      rigLength,
      headland
    };
  }

  function updateGeometryInfo() {
    try {
      const geometry = getRigGeometry();

      setText(
        "sim-headland-info",
        `Gespannlänge (Schätzung): ${formatNumber(geometry.rigLength)} m · ` +
        `Arbeitsbreite: ${formatNumber(geometry.width)} m · ` +
        `Vorgewende: ${formatNumber(geometry.headland)} m · ` +
        `Wendekreisdurchmesser: ${TURN_DIAMETER_M} m`
      );
    } catch {
      setText(
        "sim-headland-info",
        `Wendekreisdurchmesser: ${TURN_DIAMETER_M} m. ` +
        "Bitte Traktor und Anbaugerät auswählen."
      );
    }
  }

  function syncImplementWidth() {
    const implement = selectedImplement();
    if (!implement) return;

    const width = positiveValue(implement.working_width_m);

    if (width) {
      $("sim-width").value = String(width);
      $("sim-spacing").value = String(width);
    }

    updateGeometryInfo();
  }

  async function loadOptions() {
    const [fieldData, tractorData, implementData] =
      await Promise.all([
        apiGet("/api/fields"),
        apiGet("/api/tractors"),
        apiGet("/api/implements")
      ]);

    fields = Array.isArray(fieldData) ? fieldData : [];
    tractors = Array.isArray(tractorData) ? tractorData : [];
    implementsList = Array.isArray(implementData)
      ? implementData
      : [];

    fillSelect("sim-field", fields, (item) => item.name);

    fillSelect("sim-tractor", tractors, (item) => {
      const length = item.length_m
        ? ` · ${item.length_m} m`
        : "";
      return `${item.name}${length}`;
    });

    fillSelect("sim-implement", implementsList, (item) => {
      return `${item.name} · ${item.working_width_m} m`;
    });

    const workField = $("work-field")?.value;
    const workTractor = $("work-tractor")?.value;
    const workImplement = $("work-implement")?.value;

    if (
      workField &&
      fields.some((item) => String(item.id) === workField)
    ) {
      $("sim-field").value = workField;
    }

    if (
      workTractor &&
      tractors.some((item) => String(item.id) === workTractor)
    ) {
      $("sim-tractor").value = workTractor;
    }

    if (
      workImplement &&
      implementsList.some((item) => String(item.id) === workImplement)
    ) {
      $("sim-implement").value = workImplement;
    }

    syncImplementWidth();
    updateGeometryInfo();
    renderSelectedField();
  }

  // ----------------------------------------------------------
  // GeoJSON und lokale Meterprojektion
  // ----------------------------------------------------------

  function getRing(field) {
    const boundary = field?.boundary;

    if (
      !boundary ||
      boundary.type !== "Polygon" ||
      !Array.isArray(boundary.coordinates) ||
      !Array.isArray(boundary.coordinates[0])
    ) {
      throw new Error(
        "Das Feld besitzt keine gültige GeoJSON-Polygon-Grenze."
      );
    }

    const ring = boundary.coordinates[0].map((point) => {
      const lon = Number(point[0]);
      const lat = Number(point[1]);

      if (
        !Number.isFinite(lon) ||
        !Number.isFinite(lat) ||
        Math.abs(lon) > 180 ||
        Math.abs(lat) > 90
      ) {
        throw new Error(
          "Die Feldgrenze enthält ungültige GPS-Koordinaten."
        );
      }

      return [lon, lat];
    });

    if (ring.length < 4) {
      throw new Error("Die Feldgrenze hat zu wenige Eckpunkte.");
    }

    const first = ring[0];
    const last = ring[ring.length - 1];

    if (first[0] !== last[0] || first[1] !== last[1]) {
      ring.push([...first]);
    }

    return ring;
  }

  function createProjection(ring) {
    const points = ring.slice(0, -1);

    const lon0 =
      points.reduce((sum, point) => sum + point[0], 0) /
      points.length;

    const lat0 =
      points.reduce((sum, point) => sum + point[1], 0) /
      points.length;

    const cosLat = Math.cos(rad(lat0));

    if (Math.abs(cosLat) < 1e-8) {
      throw new Error(
        "Die Feldlage ist für diese Projektion ungeeignet."
      );
    }

    return {
      project([lon, lat]) {
        return vector(
          EARTH_RADIUS * rad(lon - lon0) * cosLat,
          EARTH_RADIUS * rad(lat - lat0)
        );
      },

      unproject(point) {
        return [
          lon0 + deg(point.x / (EARTH_RADIUS * cosLat)),
          lat0 + deg(point.y / EARTH_RADIUS)
        ];
      }
    };
  }

  function polygonArea(points) {
    let area = 0;

    for (let i = 0; i < points.length - 1; i++) {
      area +=
        points[i].x * points[i + 1].y -
        points[i + 1].x * points[i].y;
    }

    return Math.abs(area) / 2;
  }

  function pointInPolygon(point, polygon) {
    let inside = false;

    for (
      let i = 0, j = polygon.length - 1;
      i < polygon.length;
      j = i++
    ) {
      const a = polygon[i];
      const b = polygon[j];

      const intersects =
        (a.y > point.y) !== (b.y > point.y) &&
        point.x <
          ((b.x - a.x) * (point.y - a.y)) /
            ((b.y - a.y) || EPSILON) +
            a.x;

      if (intersects) inside = !inside;
    }

    return inside;
  }

  function resolveAngle(ring, projection, field) {
    const reference = field.reference_line;

    if (
      Array.isArray(reference) &&
      reference.length >= 2
    ) {
      const a = projection.project(reference[0]);
      const b = projection.project(
        reference[reference.length - 1]
      );

      if (distance(a, b) > 1) {
        return (
          deg(Math.atan2(b.x - a.x, b.y - a.y)) + 360
        ) % 180;
      }
    }

    const polygon = ring
      .slice(0, -1)
      .map((point) => projection.project(point));

    let longest = null;

    for (let i = 0; i < polygon.length; i++) {
      const a = polygon[i];
      const b = polygon[(i + 1) % polygon.length];
      const length = distance(a, b);

      if (!longest || length > longest.length) {
        longest = { a, b, length };
      }
    }

    if (!longest) {
      throw new Error(
        "Die Fahrtrichtung konnte nicht ermittelt werden."
      );
    }

    return (
      deg(
        Math.atan2(
          longest.b.x - longest.a.x,
          longest.b.y - longest.a.y
        )
      ) + 360
    ) % 180;
  }

  // ----------------------------------------------------------
  // Fahrspuren schneiden
  // ----------------------------------------------------------

  function clipLineToPolygon(
    polygon,
    origin,
    direction,
    normal,
    offset
  ) {
    const lineOrigin = add(origin, scale(normal, offset));
    const intersections = [];

    for (let i = 0; i < polygon.length - 1; i++) {
      const a = polygon[i];
      const b = polygon[i + 1];
      const edge = subtract(b, a);

      const denominator =
        direction.x * edge.y - direction.y * edge.x;

      if (Math.abs(denominator) < EPSILON) continue;

      const delta = subtract(a, lineOrigin);

      const t =
        (delta.x * edge.y - delta.y * edge.x) /
        denominator;

      const u =
        (delta.x * direction.y - delta.y * direction.x) /
        denominator;

      if (u >= -EPSILON && u <= 1 + EPSILON) {
        intersections.push({
          point: add(lineOrigin, scale(direction, t)),
          t
        });
      }
    }

    intersections.sort((a, b) => a.t - b.t);

    const unique = intersections.filter(
      (item, index) =>
        index === 0 ||
        Math.abs(item.t - intersections[index - 1].t) > 0.001
    );

    const segments = [];

    for (let i = 0; i + 1 < unique.length; i += 2) {
      const a = unique[i].point;
      const b = unique[i + 1].point;

      if (distance(a, b) > 1) {
        segments.push({ a, b });
      }
    }

    return segments;
  }

  function trimSegment(segment, amount) {
    const delta = subtract(segment.b, segment.a);
    const length = Math.hypot(delta.x, delta.y);

    if (length <= amount * 2 + 1) return null;

    const direction = scale(delta, 1 / length);

    return {
      a: add(segment.a, scale(direction, amount)),
      b: subtract(segment.b, scale(direction, amount))
    };
  }

  function generateLines(field, spacing, angle, headland) {
    const ring = getRing(field);
    const projection = createProjection(ring);
    const polygon = ring.map((point) => projection.project(point));
    const openPolygon = polygon.slice(0, -1);

    const center = openPolygon.reduce(
      (sum, point) =>
        add(sum, scale(point, 1 / openPolygon.length)),
      vector(0, 0)
    );

    const theta = rad(angle);
    const direction = vector(Math.sin(theta), Math.cos(theta));
    const normal = vector(direction.y, -direction.x);

    const offsets = openPolygon.map((point) => {
      return (
        (point.x - center.x) * normal.x +
        (point.y - center.y) * normal.y
      );
    });

    const minOffset = Math.min(...offsets);
    const maxOffset = Math.max(...offsets);

    const first = Math.floor(minOffset / spacing);
    const last = Math.ceil(maxOffset / spacing);

    const lines = [];

    for (let index = first; index <= last; index++) {
      const segments = clipLineToPolygon(
        polygon,
        center,
        direction,
        normal,
        index * spacing
      );

      for (const segment of segments) {
        const trimmed = trimSegment(segment, headland);
        if (!trimmed) continue;

        lines.push({
          index,
          a: trimmed.a,
          b: trimmed.b,
          length: distance(trimmed.a, trimmed.b)
        });
      }
    }

    lines.sort((a, b) => a.index - b.index);

    if (lines.length < 2) {
      throw new Error(
        "Zu wenige Fahrspuren übrig. Verringere das Vorgewende " +
        "oder den Spurabstand bzw. prüfe die Feldgröße."
      );
    }

    return { lines, ring, polygon, projection, direction };
  }
  // ----------------------------------------------------------
  // Glatte Wendebögen erzeugen
  // ----------------------------------------------------------

  function cubicBezier(p0, p1, p2, p3, t) {
    const u = 1 - t;

    return vector(
      u ** 3 * p0.x +
        3 * u ** 2 * t * p1.x +
        3 * u * t ** 2 * p2.x +
        t ** 3 * p3.x,

      u ** 3 * p0.y +
        3 * u ** 2 * t * p1.y +
        3 * u * t ** 2 * p2.y +
        t ** 3 * p3.y
    );
  }

  function makeTurn(start, end, tangentStart, tangentEnd) {
    const radius = TURN_RADIUS_M;

    const p1 = add(start, scale(tangentStart, radius));
    const p2 = subtract(end, scale(tangentEnd, radius));

    const approximateLength =
      distance(start, p1) +
      distance(p1, p2) +
      distance(p2, end);

    const steps = Math.max(
      8,
      Math.ceil(approximateLength / GPS_STEP_M)
    );

    const points = [];

    for (let i = 0; i <= steps; i++) {
      points.push(
        cubicBezier(start, p1, p2, end, i / steps)
      );
    }

    return points;
  }

  function generateRoute(generated, speedKmh, noiseM) {
    const speedMs = speedKmh / 3.6;
    const routePoints = [];
    const lines = generated.lines;
    const direction = generated.direction;
    const polygon = generated.polygon;

    let previousEnd = null;
    let previousTangent = null;

    lines.forEach((line, index) => {
      const reverse = index % 2 === 1;
      const from = reverse ? line.b : line.a;
      const to = reverse ? line.a : line.b;

      const tangent = normalize(subtract(to, from));

      if (previousEnd) {
        const turnPoints = makeTurn(
          previousEnd,
          from,
          previousTangent,
          tangent
        );

        /*
         * Keine Wendung vortäuschen, die außerhalb des Feldes
         * verläuft. Die Prüfung ist bewusst konservativ.
         */
        const outside = turnPoints.some(
          (point) => !pointInPolygon(point, polygon)
        );

        if (outside) {
          throw new Error(
            "Ein Wendebogen liegt außerhalb der Feldgrenze. " +
            "Das Feld ist für diese Kombination aus Wendekreis, " +
            "Spurabstand und Vorgewende zu eng. Passe den Winkel " +
            "oder den Spurabstand an."
          );
        }

        for (let i = 1; i < turnPoints.length; i++) {
          routePoints.push({
            point: turnPoints[i],
            lineIndex: index,
            kind: "turn",
            working: false
          });
        }
      }

      const length = distance(from, to);
      const steps = Math.max(
        2,
        Math.ceil(length / GPS_STEP_M)
      );

      for (let step = 0; step <= steps; step++) {
        const t = step / steps;
        const point = add(from, scale(subtract(to, from), t));

        if (!pointInPolygon(point, polygon)) {
          throw new Error(
            "Eine Fahrspur liegt außerhalb der Feldgrenze. " +
            "Bitte AB-Richtung und Vorgewende überprüfen."
          );
        }

        routePoints.push({
          point,
          lineIndex: index,
          kind: "lane",
          working: true
        });
      }

      previousEnd = to;
      previousTangent = tangent;
    });

    if (!routePoints.length) {
      throw new Error("Es konnten keine GPS-Punkte erzeugt werden.");
    }

    const startedAt = Date.now();
    let elapsed = 0;
    let previous = null;

    return routePoints.map((item, index) => {
      if (previous) {
        elapsed += distance(previous, item.point) / speedMs;
      }

      const phase = index * 2.399963;
      const noisyPoint = vector(
        item.point.x + noiseM * Math.cos(phase),
        item.point.y + noiseM * Math.sin(phase)
      );

      const lonLat = generated.projection.unproject(noisyPoint);

      let heading = 0;
      if (previous) {
        const delta = subtract(item.point, previous);
        heading = (
          deg(Math.atan2(delta.x, delta.y)) + 360
        ) % 360;
      }

      previous = item.point;

      return {
        lonLat,
        timestamp: new Date(
          startedAt + elapsed * 1000
        ).toISOString(),
        speed_mps: item.working ? speedMs : Math.min(speedMs, 2),
        course_deg: heading,
        line_index: item.lineIndex,
        kind: item.kind,
        working: item.working,
        simulated: true
      };
    });
  }

  // ----------------------------------------------------------
  // Leaflet-Karte
  // ----------------------------------------------------------

  function ensureMap() {
    if (map) {
      setTimeout(() => map.invalidateSize(), 100);
      return;
    }

    if (!window.L) {
      throw new Error("Leaflet ist nicht geladen.");
    }

    const element = $("work-sim-map");
    if (!element) {
      throw new Error("Das Element #work-sim-map fehlt.");
    }

    map = L.map(element).setView([51.3, 9.5], 14);

    L.tileLayer(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }
    ).addTo(map);

    layerGroup = L.layerGroup().addTo(map);
  }

  function clearLayers() {
    if (layerGroup) layerGroup.clearLayers();
    currentMarker = null;
  }

  function drawBoundary(ring) {
    const latLngs = ring.map(([lon, lat]) => [lat, lon]);

    L.polygon(latLngs, {
      color: "#16803d",
      weight: 3,
      fillColor: "#22c55e",
      fillOpacity: 0.1
    }).addTo(layerGroup);

    map.fitBounds(L.latLngBounds(latLngs), {
      padding: [24, 24]
    });
  }

  function drawLanes(lines) {
    for (const line of lines) {
      L.polyline(
        [
          [generatedLat(line.a), generatedLon(line.a)],
          [generatedLat(line.b), generatedLon(line.b)]
        ],
        {
          color: "#2563eb",
          weight: 3,
          opacity: 0.85
        }
      ).addTo(layerGroup);
    }
  }

  /*
   * Die Fahrspuren werden in lokalen Metern berechnet.
   * Die Konvertierung für Leaflet erfolgt über die Projektion,
   * die für die aktuelle Simulation gespeichert wird.
   */
  let activeProjection = null;

  function generatedLat(point) {
    return activeProjection.unproject(point)[1];
  }

  function generatedLon(point) {
    return activeProjection.unproject(point)[0];
  }

  function drawRoute(routePoints) {
    const lanePoints = [];
    let previousKind = null;
    let previousLineIndex = null;

    for (const point of routePoints) {
      if (
        point.kind !== previousKind ||
        point.line_index !== previousLineIndex
      ) {
        lanePoints.length = 0;
      }

      lanePoints.push([
        point.lonLat[1],
        point.lonLat[0]
      ]);

      if (lanePoints.length >= 2) {
        L.polyline(
          lanePoints.slice(-2),
          {
            color: point.kind === "turn" ? "#0ea5e9" : "#f97316",
            weight: point.kind === "turn" ? 3 : 4,
            opacity: 0.9
          }
        ).addTo(layerGroup);
      }

      previousKind = point.kind;
      previousLineIndex = point.line_index;
    }
  }

  function renderSelectedField() {
    const field = selectedField();

    try {
      ensureMap();
      clearLayers();

      if (!field) {
        message("Bitte ein Feld auswählen.");
        return;
      }

      const ring = getRing(field);
      const projection = createProjection(ring);
      activeProjection = projection;

      drawBoundary(ring);

      const polygon = ring.map((point) => projection.project(point));
      const areaHa = polygonArea(polygon) / 10000;

      setText(
        "sim-area",
        `${formatNumber(areaHa, 2)} ha`
      );

      const angle = resolveAngle(ring, projection, field);
      $("sim-angle").value = String(Math.round(angle));

      const hasReference =
        Array.isArray(field.reference_line) &&
        field.reference_line.length >= 2;

      setText(
        "sim-reference-info",
        hasReference
          ? `AB-Richtung aus gespeicherter Referenzlinie: ${formatNumber(angle)}°.`
          : `AB-Richtung anhand der längsten Feldkante: ${formatNumber(angle)}°.`
      );

      updateGeometryInfo();
      message("Feld geladen. Simulation bereit.");
    } catch (error) {
      message(error.message, true);
    }
  }

  // ----------------------------------------------------------
  // Wiedergabe und Kennzahlen
  // ----------------------------------------------------------

  function updateStats() {
    setText(
      "sim-points",
      route.length
        ? `${Math.min(routeIndex + 1, route.length)} / ${route.length}`
        : "0"
    );

    const progress = route.length
      ? Math.round(
          routeIndex / Math.max(1, route.length - 1) * 100
        )
      : 0;

    setText("sim-progress", `${progress} %`);

    setText(
      "sim-distance",
      drivenDistanceM >= 1000
        ? `${formatNumber(drivenDistanceM / 1000, 2)} km`
        : `${Math.round(drivenDistanceM)} m`
    );
  }

  function stopTimer() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function resetSimulation() {
    stopTimer();
    animationToken++;

    route = [];
    routeIndex = 0;
    running = false;
    paused = false;
    finished = false;

    drivenDistanceM = 0;
    lastPoint = null;

    if ($("sim-start")) $("sim-start").disabled = false;
    if ($("sim-pause")) $("sim-pause").disabled = true;
    if ($("sim-resume")) $("sim-resume").disabled = true;

    status("Bereit");
    updateStats();
    renderSelectedField();
  }

  function playNextPoint() {
    if (!running || paused || finished) return;

    if (routeIndex >= route.length) {
      stopTimer();

      running = false;
      finished = true;

      $("sim-start").disabled = false;
      $("sim-pause").disabled = true;
      $("sim-resume").disabled = true;

      status("Abgeschlossen");
      message(
        `Simulation abgeschlossen: ${route.length} synthetische GPS-Punkte. ` +
        "Es wurden keine Daten gespeichert."
      );

      updateStats();
      return;
    }

    const point = route[routeIndex];
    const [lon, lat] = point.lonLat;

    if (lastPoint) {
      const latFactor = 111320;
      const lonFactor = 111320 * Math.cos(rad(lat));

      drivenDistanceM += Math.hypot(
        (lon - lastPoint.lon) * lonFactor,
        (lat - lastPoint.lat) * latFactor
      );
    }

    const latLng = [lat, lon];

    if (!currentMarker) {
      currentMarker = L.circleMarker(latLng, {
        radius: 7,
        color: "#ffffff",
        weight: 2,
        fillColor: "#f97316",
        fillOpacity: 1
      }).addTo(layerGroup);
    } else {
      currentMarker.setLatLng(latLng);
    }

    lastPoint = {
      lon,
      lat
    };

    routeIndex++;
    updateStats();
  }

  // ----------------------------------------------------------
  // Simulation starten
  // ----------------------------------------------------------

  function startSimulation() {
    resetSimulation();

    try {
      const field = selectedField();
      if (!field) {
        throw new Error("Bitte ein Feld auswählen.");
      }

      const geometry = getRigGeometry();

      const width = readNumber("sim-width", 0.5, 30);
      const spacing = readNumber("sim-spacing", 0.5, 60);
      const speed = readNumber("sim-speed", 1, 25);
      const noise = readNumber("sim-noise", 0, 2);
      const angle = readNumber("sim-angle", 0, 179);

      if (width > Number(geometry.implement.working_width_m)) {
        message(
          "Hinweis: Die eingegebene Arbeitsbreite ist größer als " +
          "die gespeicherte Gerätearbeitsbreite.",
          true
        );
      }

      const generated = generateLines(
        field,
        spacing,
        angle,
        geometry.headland
      );

      activeProjection = generated.projection;

      route = generateRoute(
        generated,
        speed,
        noise
      );

      clearLayers();
      drawBoundary(generated.ring);
      drawLanes(generated.lines);
      drawRoute(route);

      setText("sim-lines", String(generated.lines.length));

      routeIndex = 0;
      drivenDistanceM = 0;
      lastPoint = null;

      running = true;
      paused = false;
      finished = false;

      $("sim-start").disabled = true;
      $("sim-pause").disabled = false;
      $("sim-resume").disabled = true;

      status("Läuft");
      message(
        `Simulation läuft. ${generated.lines.length} Fahrspuren, ` +
        `Vorgewende ${formatNumber(geometry.headland)} m, ` +
        `Wendekreis ${TURN_DIAMETER_M} m. GPS-Daten sind synthetisch.`
      );

      updateStats();

      const token = ++animationToken;

      timer = setInterval(() => {
        if (token !== animationToken) return;
        playNextPoint();
      }, ANIMATION_INTERVAL_MS);
    } catch (error) {
      stopTimer();
      running = false;

      status("Fehler");
      message(error.message, true);

      if ($("sim-start")) $("sim-start").disabled = false;
    }
  }

  function pauseSimulation() {
    if (!running || paused) return;

    paused = true;
    stopTimer();

    $("sim-pause").disabled = true;
    $("sim-resume").disabled = false;

    status("Pausiert");
    message("Simulation pausiert.");
  }

  function resumeSimulation() {
    if (!running || !paused || finished) return;

    paused = false;

    $("sim-pause").disabled = false;
    $("sim-resume").disabled = true;

    status("Läuft");
    message("Simulation fortgesetzt.");

    const token = ++animationToken;

    timer = setInterval(() => {
      if (token !== animationToken) return;
      playNextPoint();
    }, ANIMATION_INTERVAL_MS);
  }

  // ----------------------------------------------------------
  // Ereignisse und Initialisierung
  // ----------------------------------------------------------

  function bindEvents() {
    $("sim-field").addEventListener("change", () => {
      resetSimulation();
      renderSelectedField();
    });

    $("sim-tractor").addEventListener("change", () => {
      resetSimulation();
      updateGeometryInfo();
    });

    $("sim-implement").addEventListener("change", () => {
      resetSimulation();
      syncImplementWidth();
    });

    $("sim-width").addEventListener("change", updateGeometryInfo);

    $("sim-spacing").addEventListener("change", () => {
      if ($("sim-spacing").value.trim() === "") return;
      updateGeometryInfo();
    });

    $("sim-start").addEventListener("click", startSimulation);
    $("sim-pause").addEventListener("click", pauseSimulation);
    $("sim-resume").addEventListener("click", resumeSimulation);

    $("sim-reset").addEventListener("click", () => {
      resetSimulation();
      message("Simulation zurückgesetzt.");
    });

    document
      .querySelectorAll('nav [data-section="work"]')
      .forEach((button) => {
        button.addEventListener("click", () => {
          setTimeout(() => {
            if (!map) return;
            map.invalidateSize();
            renderSelectedField();
          }, 150);
        });
      });
  }

  async function init() {
    const required = [
      "sim-field",
      "sim-implement",
      "sim-width",
      "sim-speed",
      "sim-angle",
      "sim-noise",
      "sim-start",
      "sim-pause",
      "sim-resume",
      "sim-reset",
      "work-sim-map",
      "sim-status",
      "sim-message"
    ];

    const missing = required.filter((id) => !$(id));

    if (missing.length) {
      console.error(
        "PyTrac Simulator: Fehlende HTML-Elemente:",
        missing
      );
      return;
    }

    try {
      ensureExtraControls();
      ensureMap();
      bindEvents();
      await loadOptions();
    } catch (error) {
      status("Nicht verfügbar");
      message(
        "Simulator konnte nicht initialisiert werden: " +
        error.message,
        true
      );
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, {
      once: true
    });
  } else {
    init();
  }
})();
