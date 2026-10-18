"use strict";

let historyMap = null;
let historyTrackLayer = null;
let historyFieldLayer = null;
let selectedHistorySession = null;
let historySessions = [];

function initHistoryMap() {
  if (historyMap) return;

  historyMap = L.map("history-map").setView([51.3, 9.5], 14);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(historyMap);

  historyFieldLayer = L.layerGroup().addTo(historyMap);
  historyTrackLayer = L.layerGroup().addTo(historyMap);
}

function historyEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function historyDate(value) {
  if (!value) return "–";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleString("de-DE");
}

function distanceBetween(a, b) {
  const radius = 6371000;
  const rad = degrees => degrees * Math.PI / 180;

  const lat1 = rad(a.latitude);
  const lat2 = rad(b.latitude);
  const dLat = lat2 - lat1;
  const dLon = rad(b.longitude - a.longitude);

  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) *
    Math.sin(dLon / 2) ** 2;

  return 2 * radius * Math.asin(Math.sqrt(Math.min(1, h)));
}

function calculateTrackDistance(points) {
  let total = 0;

  for (let i = 1; i < points.length; i++) {
    total += distanceBetween(points[i - 1], points[i]);
  }

  return total;
}

function formatDistance(meters) {
  if (meters >= 1000) {
    return (meters / 1000).toLocaleString("de-DE", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }) + " km";
  }

  return Math.round(meters).toLocaleString("de-DE") + " m";
}

async function loadHistory() {
  const container = document.getElementById("history-list");
  container.innerHTML = "<p>Lade Arbeitsgänge …</p>";

  try {
    historySessions = await request("/api/work-sessions");
    renderHistoryList();

  } catch (error) {
    container.textContent =
      "Arbeitsgänge konnten nicht geladen werden: " + error.message;
  }
}

function renderHistoryList() {
  const container = document.getElementById("history-list");

  if (!historySessions.length) {
    container.innerHTML =
      '<article class="record-card">Noch keine Arbeitsgänge gespeichert.</article>';
    return;
  }

  container.innerHTML = historySessions.map(session => {
    const active = Number(session.id) ===
      Number(selectedHistorySession?.id);

    return `
      <article class="record-card history-card ${active ? "selected" : ""}">
        <button
          type="button"
          class="history-select"
          data-history-select="${Number(session.id)}"
        >
          <strong>${historyEscape(session.name || "Arbeitsgang")}</strong>
          <span>${historyEscape(historyDate(session.started_at))}</span>
          <span>Feld: ${historyEscape(session.field_name || "–")}</span>
          <span>Traktor: ${historyEscape(session.tractor_name || "–")}</span>
          <span>Gerät: ${historyEscape(session.implement_name || "–")}</span>
          <span>Status: ${historyEscape(session.status)}</span>
          <span>GPS-Punkte: ${Number(session.point_count || 0)}</span>
        </button>
      </article>`;
  }).join("");

  container.querySelectorAll("[data-history-select]").forEach(button => {
    button.addEventListener("click", () => {
      selectHistorySession(Number(button.dataset.historySelect));
    });
  });
}

async function selectHistorySession(id) {
  const session = historySessions.find(
    item => Number(item.id) === Number(id)
  );

  if (!session) return;

  selectedHistorySession = session;
  renderHistoryList();

  document.getElementById("history-map-title").textContent =
    session.name || `Arbeitsgang #${session.id}`;

  document.getElementById("history-details").textContent =
    "Lade GPS-Strecke …";

  document.getElementById("history-delete").disabled =
    ["running", "paused"].includes(session.status);

  initHistoryMap();
  historyTrackLayer.clearLayers();
  historyFieldLayer.clearLayers();

  try {
    const [trackData, fieldData] = await Promise.all([
      request(`/api/work-sessions/${id}/track`),
      request("/api/fields")
    ]);

    const points = (trackData.points || []).filter(point =>
      Number.isFinite(Number(point.latitude)) &&
      Number.isFinite(Number(point.longitude))
    );

    const latLngs = points.map(point => [
      Number(point.latitude),
      Number(point.longitude)
    ]);

    if (latLngs.length >= 2) {
      const line = L.polyline(latLngs, {
        color: "#e07820",
        weight: 4,
        opacity: 0.9
      }).addTo(historyTrackLayer);

      L.circleMarker(latLngs[0], {
        radius: 6,
        color: "#17643a",
        fillColor: "#2b8a50",
        fillOpacity: 1
      }).bindPopup("Start").addTo(historyTrackLayer);

      L.circleMarker(latLngs[latLngs.length - 1], {
        radius: 6,
        color: "#b42318",
        fillColor: "#e34b40",
        fillOpacity: 1
      }).bindPopup("Ende").addTo(historyTrackLayer);

      historyMap.fitBounds(line.getBounds(), {
        padding: [25, 25],
        maxZoom: 18
      });

    } else if (latLngs.length === 1) {
      historyMap.setView(latLngs[0], 18);

      L.marker(latLngs[0])
        .bindPopup("Einziger gespeicherter GPS-Punkt")
        .addTo(historyTrackLayer);
    }

    const field = fieldData.find(
      item => Number(item.id) === Number(session.field_id)
    );

    if (field?.boundary) {
      L.geoJSON(field.boundary, {
        style: {
          color: "#17643a",
          weight: 2,
          fillColor: "#2b8a50",
          fillOpacity: 0.08
        }
      }).addTo(historyFieldLayer);

if (latLngs.length < 2) {
  const fieldLayers = historyFieldLayer.getLayers();

  if (fieldLayers.length > 0) {
    const fieldBounds = L.featureGroup(fieldLayers).getBounds();

    if (fieldBounds.isValid()) {
      historyMap.fitBounds(fieldBounds, {
        padding: [25, 25],
        maxZoom: 17
      });
    }
  }
}
    }

    const distance = calculateTrackDistance(points);

    document.getElementById("history-details").innerHTML = `
      <p><strong>Start:</strong> ${historyEscape(historyDate(session.started_at))}</p>
      <p><strong>Ende:</strong> ${historyEscape(historyDate(session.finished_at))}</p>
      <p><strong>Gefahrene Strecke:</strong> ${historyEscape(formatDistance(distance))}</p>
      <p><strong>GPS-Punkte:</strong> ${points.length}</p>
      ${points.length < 2
        ? "<p class='muted'>Für eine Streckenlinie werden mindestens zwei GPS-Punkte benötigt.</p>"
        : ""}
    `;

    setTimeout(() => historyMap.invalidateSize(), 100);

  } catch (error) {
    document.getElementById("history-details").textContent =
      "Strecke konnte nicht geladen werden: " + error.message;
  }
}

async function deleteHistorySession() {
  const session = selectedHistorySession;

  if (!session) return;

  if (["running", "paused"].includes(session.status)) {
    alert("Laufende oder pausierte Arbeitsgänge können nicht gelöscht werden.");
    return;
  }

  const confirmed = confirm(
    `Arbeitsgang "${session.name}" (ID ${session.id}) wirklich löschen?\n\n` +
    "Die zugehörigen GPS-Punkte und Flächendaten werden ebenfalls gelöscht."
  );

  if (!confirmed) return;

  const button = document.getElementById("history-delete");
  button.disabled = true;

  try {
    await request(`/api/work-sessions/${session.id}`, {
      method: "DELETE"
    });

    selectedHistorySession = null;
    historyTrackLayer?.clearLayers();
    historyFieldLayer?.clearLayers();

    document.getElementById("history-map-title").textContent =
      "Gefahrene Strecke";

    document.getElementById("history-details").textContent =
      "Bitte einen Arbeitsgang auswählen.";

    await loadHistory();

    notice("Arbeitsgang und zugehörige GPS-Daten wurden gelöscht.");

  } catch (error) {
    alert("Löschen fehlgeschlagen: " + error.message);
    button.disabled = false;
  }
}

document.getElementById("history-refresh").addEventListener(
  "click",
  loadHistory
);

document.getElementById("history-delete").addEventListener(
  "click",
  deleteHistorySession
);
