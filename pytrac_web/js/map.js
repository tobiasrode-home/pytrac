
"use strict";

let fieldMap = null;
let fieldLayers = null;
let fieldMapReady = false;

function initFieldMap(record = null) {
  $("field-map-container").classList.remove("hidden");

  if (!fieldMapReady) {
    fieldMap = L.map("field-map").setView([51.3, 9.5], 14);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors"
    }).addTo(fieldMap);

    fieldLayers = new L.FeatureGroup();
    fieldMap.addLayer(fieldLayers);

    fieldMap.addControl(new L.Control.Draw({
      position: "topleft",
      draw: {
        polygon: {
          allowIntersection: false,
          showArea: true,
          shapeOptions: {
            color: "#17643a",
            fillColor: "#2b8a50",
            fillOpacity: 0.25
          }
        },
        polyline: {
          shapeOptions: { color: "#e07820", weight: 4 }
        },
        rectangle: false,
        circle: false,
        circlemarker: false,
        marker: false
      },
      edit: { featureGroup: fieldLayers, remove: true }
    }));

    fieldMap.on(L.Draw.Event.CREATED, event => {
      const layer = event.layer;

      if (layer instanceof L.Polygon) {
        removeGeometry("polygon");
      } else if (layer instanceof L.Polyline) {
        removeGeometry("line");
      }

      fieldLayers.addLayer(layer);
      syncMapToForm();
    });

    fieldMap.on(L.Draw.Event.EDITED, syncMapToForm);
    fieldMap.on(L.Draw.Event.DELETED, syncMapToForm);

    $("map-clear").addEventListener("click", () => {
      fieldLayers.clearLayers();
      syncMapToForm();
    });

    $("map-fit").addEventListener("click", fitFieldMap);

    fieldMapReady = true;
  }

  fieldLayers.clearLayers();

  // Das Backend liefert boundary als [[lon, lat], ...].
  if (Array.isArray(record?.boundary) && record.boundary.length >= 4) {
    const points = record.boundary.map(([lon, lat]) => [lat, lon]);

    fieldLayers.addLayer(L.polygon(points, {
      color: "#17643a",
      fillColor: "#2b8a50",
      fillOpacity: 0.25
    }));
  }

  if (Array.isArray(record?.reference_line) &&
      record.reference_line.length >= 2) {
    const points = record.reference_line.map(([lon, lat]) => [lat, lon]);

    fieldLayers.addLayer(L.polyline(points, {
      color: "#e07820",
      weight: 4
    }));
  }

  setTimeout(() => {
    fieldMap.invalidateSize();
    fitFieldMap();
    syncMapToForm();
  }, 200);
}

function removeGeometry(type) {
  const remove = [];

  fieldLayers.eachLayer(layer => {
    if (type === "polygon" && layer instanceof L.Polygon) {
      remove.push(layer);
    } else if (
      type === "line" &&
      layer instanceof L.Polyline &&
      !(layer instanceof L.Polygon)
    ) {
      remove.push(layer);
    }
  });

  remove.forEach(layer => fieldLayers.removeLayer(layer));
}

function syncMapToForm() {
  if (!fieldMapReady || current !== "fields") return;

  let boundary = null;
  let referenceLine = [];

  fieldLayers.eachLayer(layer => {
    if (layer instanceof L.Polygon) {
      const rings = layer.getLatLngs();
      const ring = rings[0];

      boundary = ring.map(point => [point.lng, point.lat]);

      // Den Polygonring ausdrücklich schließen.
      if (boundary.length > 0) {
        const first = boundary[0];
        const last = boundary[boundary.length - 1];

        if (first[0] !== last[0] || first[1] !== last[1]) {
          boundary.push([...first]);
        }
      }
    } else if (layer instanceof L.Polyline) {
      referenceLine = layer.getLatLngs().map(point => [
        point.lng, point.lat
      ]);
    }
  });

  const boundaryInput = $("input-boundary");
  const referenceInput = $("input-reference_line");

  if (boundaryInput) {
    boundaryInput.value = boundary
      ? JSON.stringify(boundary, null, 2)
      : "";
  }

  if (referenceInput) {
    referenceInput.value = JSON.stringify(referenceLine, null, 2);
  }

  const area = $("map-area");

  if (boundary && boundary.length >= 4) {
    const approximateArea = calculateMapArea(boundary);

    area.textContent = "Kartenschätzung: " +
      (approximateArea / 10000).toLocaleString("de-DE", {
        minimumFractionDigits: 3,
        maximumFractionDigits: 3
      }) +
      " ha. Die endgültige Fläche wird serverseitig berechnet.";
  } else {
    area.textContent = "Noch keine Feldgrenze eingezeichnet.";
  }
}

function calculateMapArea(ring) {
  if (!ring || ring.length < 4) return 0;

  const openRing = ring.slice(0, -1);

  const latMean = openRing.reduce(
    (sum, point) => sum + point[1], 0
  ) / openRing.length;

  const lon0 = ring[0][0];

  const projected = ring.map(([lon, lat]) => [
    (lon - lon0) * 111320 * Math.cos(latMean * Math.PI / 180),
    (lat - latMean) * 110540
  ]);

  let sum = 0;

  for (let i = 0; i < projected.length - 1; i++) {
    sum += projected[i][0] * projected[i + 1][1]
      - projected[i + 1][0] * projected[i][1];
  }

  return Math.abs(sum) / 2;
}

function fitFieldMap() {
  if (!fieldMap || !fieldLayers ||
      fieldLayers.getLayers().length === 0) return;

  const bounds = fieldLayers.getBounds();

  if (bounds.isValid()) {
    fieldMap.fitBounds(bounds, {
      padding: [25, 25],
      maxZoom: 18
    });
  }
}
