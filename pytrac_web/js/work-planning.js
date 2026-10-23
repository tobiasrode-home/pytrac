/* Arbeitsplanung – wird in die vorhandene Arbeitsgang-Sektion integriert. */
(() => {
  "use strict";

  const $ = id => document.getElementById(id);
  const state = {
    fields: [], tractors: [], implements: [], plans: [],
    map: null, boundaryLayer: null, edgeLayer: null, startMarker: null,
    boundary: [], startPoint: null
  };

  const dateInputValue = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  const timeInputValue = () => {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  };
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers }
    });
    const raw = await response.text();
    let body = null;
    if (raw) {
      try { body = JSON.parse(raw); } catch { body = raw; }
    }
    if (!response.ok) {
      const detail = body && typeof body === "object" ? body.detail : body;
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return body;
  }

  function mount() {
    const section = $("section-work");
    if (!section || $("work-planning-panel")) return;

    const panel = document.createElement("article");
    panel.id = "work-planning-panel";
    panel.className = "panel";
    panel.innerHTML = `
      <div class="section-heading">
        <div><h3>Arbeitsplanung</h3><p class="muted">Konfiguration für eine spätere Spurplanung speichern.</p></div>
        <button type="button" id="wp-refresh">Aktualisieren</button>
      </div>
      <div class="form-grid">
        <label>Feld<select id="wp-field" required><option value="">Bitte auswählen</option></select></label>
        <label>Traktor<select id="wp-tractor" required><option value="">Bitte auswählen</option></select></label>
        <label>Anbaugerät<select id="wp-implement" required><option value="">Bitte auswählen</option></select></label>
        <label>Bezeichnung<input id="wp-name" maxlength="100" value="Arbeitsplanung" required></label>
        <label>Vorgewende-Tiefe (Arbeitsbreiten)<input id="wp-depth-widths" type="number" min="0.1" max="20" step="1" value="1" required></label>
        <label>Vorgewende-Modus<select id="wp-headland-mode"><option value="all_around">Rundum</option><option value="headlands_only">Nur Feldenden</option></select></label>
        <label>Wendemanöver<select id="wp-maneuver"><option value="u_turn">U-Wende</option><option value="y_turn">Y-Wende</option></select></label>
        <label>Geschwindigkeit (km/h)<input id="wp-speed" type="number" min="0.1" max="30" step="0.5" value="8"></label>
        <label class="wp-check"><span>Beetbau (nur U-Wende)</span><input id="wp-beet" type="checkbox"></label>
      </div>
      <h4>Feldgrenze, Referenzkante und Startpunkt</h4>
      <p class="muted">Wähle eine Referenzkante separat und klicke anschließend direkt auf die Feldgrenze, um den Startpunkt zu setzen.</p>
      <label>Referenzkante<select id="wp-edge"><option value="0">Kante 1</option></select></label>
      <div id="wp-map" role="img" aria-label="Feldgrenze mit Referenzkante und Startpunkt"></div>
      <p id="wp-map-status" class="muted">Bitte ein Feld auswählen.</p>
      <div class="form-actions"><button type="button" class="primary" id="wp-save">Planung speichern</button><button type="button" id="wp-reset">Zurücksetzen</button></div>
      <h4>Gespeicherte Planungen</h4><div id="wp-list" class="records-list"></div>
      <p id="wp-message" role="status" class="muted"></p>`;
    section.appendChild(panel);

    $("wp-date").value = dateInputValue();
    $("wp-time").value = timeInputValue();
    $("wp-field").addEventListener("change", () => loadField().catch(showError));
    $("wp-edge").addEventListener("change", drawMap);
    $("wp-maneuver").addEventListener("change", () => {
      $("wp-beet").disabled = $("wp-maneuver").value !== "u_turn";
      if ($("wp-beet").disabled) $("wp-beet").checked = false;
    });
    $("wp-save").addEventListener("click", savePlan);
    $("wp-refresh").addEventListener("click", () => refresh().catch(showError));
    $("wp-reset").addEventListener("click", resetForm);
    refresh().catch(showError);
  }

  async function refresh() {
    const [fields, tractors, implementsList, plans] = await Promise.all([
      api("/api/fields"), api("/api/tractors"), api("/api/implements"), api("/api/work-plans")
    ]);
    state.fields = fields;
    state.tractors = tractors;
    state.implements = implementsList;
    state.plans = plans;
    $("wp-field").innerHTML = makeOptions(fields);
    $("wp-tractor").innerHTML = makeOptions(tractors);
    $("wp-implement").innerHTML = makeOptions(implementsList);
    renderPlans();
    await loadField();
  }

  function makeOptions(items) {
    return '<option value="">Bitte auswählen</option>' +
      items.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
  }

  async function loadField() {
    const field = state.fields.find(item => item.id === Number($("wp-field").value));
    state.boundary = field?.boundary || [];
    state.startPoint = null;
    if (state.startMarker) { state.startMarker.remove(); state.startMarker = null; }
    const edgeSelect = $("wp-edge");
    const count = Math.max(1, state.boundary.length - 1);
    edgeSelect.innerHTML = Array.from({ length: count }, (_, i) =>
      `<option value="${i}">Kante ${i + 1}</option>`).join("");
    drawMap();
  }

  function drawMap() {
    if (!window.L || !$("wp-map")) return;
    if (!state.map) {
      state.map = L.map("wp-map");
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 20, attribution: "&copy; OpenStreetMap"
      }).addTo(state.map);
      state.map.on("click", event => {
        const point = nearestBoundaryPoint(event.latlng);
        if (!point) {
          $("wp-map-status").textContent = "Bitte direkt auf die Feldgrenze klicken.";
          return;
        }
        state.startPoint = { lat: point.lat, lon: point.lng };
        if (state.startMarker) state.startMarker.remove();
        state.startMarker = L.marker(point).addTo(state.map).bindTooltip("Startpunkt").openTooltip();
        $("wp-map-status").textContent = `Startpunkt: ${point.lat.toFixed(6)}, ${point.lng.toFixed(6)}`;
      });
    }
    if (state.boundaryLayer) state.boundaryLayer.remove();
    if (state.edgeLayer) state.edgeLayer.remove();
    if (state.boundary.length < 4) {
      $("wp-map-status").textContent = "Bitte ein Feld mit gültiger Feldgrenze auswählen.";
      return;
    }
    // Feld-API liefert [Längengrad, Breitengrad]; Leaflet benötigt [Breitengrad, Längengrad].
    const latlngs = state.boundary.map(point => [point[1], point[0]]);
    state.boundaryLayer = L.polygon(latlngs, { color: "#17643a", weight: 3, fillOpacity: 0.08 }).addTo(state.map);
    const edgeIndex = Number($("wp-edge").value || 0);
    state.edgeLayer = L.polyline([latlngs[edgeIndex], latlngs[edgeIndex + 1]], {
      color: "#e07820", weight: 6
    }).addTo(state.map);
    state.map.fitBounds(state.boundaryLayer.getBounds(), { padding: [20, 20] });
    $("wp-map-status").textContent = "Orange markierte Referenzkante. Klicke auf die Feldgrenze für den Startpunkt.";
    if (state.startMarker) state.startMarker.addTo(state.map);
    setTimeout(() => state.map.invalidateSize(), 100);
  }

  function nearestBoundaryPoint(latlng) {
    if (!state.map || state.boundary.length < 2) return null;
    const p = state.map.latLngToLayerPoint(latlng);
    const points = state.boundary.map(c => state.map.latLngToLayerPoint([c[1], c[0]]));
    let best = null;
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i], b = points[i + 1];
      const dx = b.x - a.x, dy = b.y - a.y;
      const denom = dx * dx + dy * dy;
      const t = Math.max(0, Math.min(1, denom ? ((p.x-a.x)*dx + (p.y-a.y)*dy)/denom : 0));
      const candidate = L.point(a.x + t*dx, a.y + t*dy);
      const distance = p.distanceTo(candidate);
      if (!best || distance < best.distance) {
        const ll = state.map.layerPointToLatLng(candidate);
        best = { lat: ll.lat, lng: ll.lng, distance };
      }
    }
    return best && best.distance <= 18 ? L.latLng(best.lat, best.lng) : null;
  }

  async function savePlan() {
    try {
      if (!$("wp-field").value || !$("wp-tractor").value || !$("wp-implement").value)
        throw new Error("Bitte Feld, Traktor und Anbaugerät auswählen.");
      if (!state.startPoint) throw new Error("Bitte einen Startpunkt auf der Feldgrenze setzen.");
      const payload = {
        field_id: Number($("wp-field").value),
        tractor_id: Number($("wp-tractor").value),
        implement_id: Number($("wp-implement").value),
        planning_date: $("wp-date").value,
        planning_time: $("wp-time").value,
        name: $("wp-name").value.trim(),
        maneuver_mode: $("wp-maneuver").value,
        headland_depth_m: Number($("wp-depth-m").value),
        headland_depth_widths: Number($("wp-depth-widths").value),
        headland_mode: $("wp-headland-mode").value,
        target_speed_kmh: Number($("wp-speed").value),
        beet_farming: $("wp-beet").checked,
        reference_edge_index: Number($("wp-edge").value),
        start_point: state.startPoint
      };
      if (!payload.planning_date || !payload.planning_time || !payload.name)
        throw new Error("Bitte Bezeichnung, Datum und Uhrzeit ausfüllen.");
      await api("/api/work-plans", { method: "POST", body: JSON.stringify(payload) });
      $("wp-message").textContent = "Arbeitsplanung gespeichert.";
      await refresh();
    } catch (error) { showError(error); }
  }

  function renderPlans() {
    const container = $("wp-list");
    if (!container) return;
    if (!state.plans.length) {
      container.innerHTML = '<p class="muted">Noch keine Arbeitsplanungen gespeichert.</p>';
      return;
    }
    container.innerHTML = state.plans.map(plan => {
      const field = state.fields.find(x => x.id === plan.field_id)?.name || `Feld ${plan.field_id}`;
      const tractor = state.tractors.find(x => x.id === plan.tractor_id)?.name || `Traktor ${plan.tractor_id}`;
      const implement = state.implements.find(x => x.id === plan.implement_id)?.name || `Anbaugerät ${plan.implement_id}`;
      return `<article class="record-card"><div><h3>${escapeHtml(plan.name)}</h3>
        <p>${escapeHtml(field)} · ${escapeHtml(tractor)} · ${escapeHtml(implement)}</p>
        <p>${escapeHtml(plan.planning_date)} ${escapeHtml(plan.planning_time)} ·
        ${plan.maneuver_mode === "u_turn" ? "U-Wende" : "Y-Wende"} ·
        ${escapeHtml(plan.headland_depth_widths)} Arbeitsbreiten</p></div>
        <div class="record-actions"><button type="button" data-wp-load="${plan.id}">Laden</button>
        <button type="button" class="danger" data-wp-delete="${plan.id}">Löschen</button></div></article>`;
    }).join("");
    container.querySelectorAll("[data-wp-load]").forEach(button =>
      button.addEventListener("click", () => loadPlan(Number(button.dataset.wpLoad))));
    container.querySelectorAll("[data-wp-delete]").forEach(button =>
      button.addEventListener("click", async () => {
        if (!confirm("Diese Arbeitsplanung wirklich löschen?")) return;
        try {
          await api(`/api/work-plans/${button.dataset.wpDelete}`, { method: "DELETE" });
          await refresh();
        } catch (error) { showError(error); }
      }));
  }

  async function loadPlan(id) {
    const plan = state.plans.find(item => item.id === id);
    if (!plan) return;
    $("wp-field").value = String(plan.field_id);
    $("wp-tractor").value = String(plan.tractor_id);
    $("wp-implement").value = String(plan.implement_id);
    $("wp-date").value = plan.planning_date;
    $("wp-time").value = plan.planning_time.slice(0, 5);
    $("wp-name").value = plan.name;
    $("wp-depth-m").value = plan.headland_depth_m;
    $("wp-depth-widths").value = plan.headland_depth_widths;
    $("wp-headland-mode").value = plan.headland_mode;
    $("wp-maneuver").value = plan.maneuver_mode;
    $("wp-speed").value = plan.target_speed_kmh;
    $("wp-beet").checked = plan.beet_farming;
    $("wp-edge").value = String(plan.reference_edge_index);
    $("wp-maneuver").dispatchEvent(new Event("change"));
    await loadField();
    state.startPoint = plan.start_point;
    if (state.startPoint && state.map) {
      state.startMarker = L.marker([state.startPoint.lat, state.startPoint.lon]).addTo(state.map).bindTooltip("Startpunkt");
      $("wp-map-status").textContent = `Geladener Startpunkt: ${state.startPoint.lat.toFixed(6)}, ${state.startPoint.lon.toFixed(6)}`;
    }
  }

  function resetForm() {
    $("wp-date").value = dateInputValue();
    $("wp-time").value = timeInputValue();
    $("wp-name").value = "Arbeitsplanung";
    $("wp-depth-m").value = "5";
    $("wp-depth-widths").value = "1";
    $("wp-headland-mode").value = "all_around";
    $("wp-maneuver").value = "u_turn";
    $("wp-speed").value = "8";
    $("wp-beet").checked = false;
    $("wp-beet").disabled = false;
    state.startPoint = null;
    if (state.startMarker) { state.startMarker.remove(); state.startMarker = null; }
    $("wp-message").textContent = "";
  }

  function showError(error) {
    const target = $("wp-message");
    if (target) target.textContent = `Fehler: ${error.message || error}`;
  }

  document.addEventListener("DOMContentLoaded", mount);
  document.addEventListener("click", event => {
    if (event.target.closest('nav [data-section="work"], [data-go="work"]')) {
      setTimeout(() => {
        if ($("work-planning-panel")) refresh().catch(showError);
      }, 0);
    }
  });
})();
