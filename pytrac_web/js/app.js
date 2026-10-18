"use strict";

const $ = id => document.getElementById(id);

let current = "dashboard";
let records = [];
let editingId = null;

const configs = {
  fields: {
    title: "Felder",
    api: "/api/fields",
    fields: [
      ["name", "Feldname", "text", true, "", ""],
      ["boundary", "Feldgrenze (GeoJSON)", "json", true, "", ""],
      ["reference_line", "Referenzlinie (JSON)", "json", false, "", []]
    ]
  },

  tractors: {
    title: "Traktoren",
    api: "/api/tractors",
    fields: [
      ["name", "Name", "text", true, "", ""],
      ["length_m", "Länge (m)", "number", true, "", ""],
      ["width_m", "Breite (m)", "number", true, "", ""],
      ["gps_offset_length_m", "GPS-Längsversatz (m)", "number", false, "", 0],
      ["gps_offset_width_m", "GPS-Seitenversatz (m)", "number", false, "", 0],
      ["turning_radius_m", "Wenderadius (m)", "number", true, "", ""]
    ]
  },

  implements: {
    title: "Anbaugeräte",
    api: "/api/implements",
    fields: [
      ["name", "Name", "text", true, "", ""],
      ["length_m", "Länge (m)", "number", true, "", ""],
      ["working_width_m", "Arbeitsbreite (m)", "number", true, "", ""],
      [
        "mount_type", "Anbauposition", "select", true, "", "rear",
        [
          ["front", "Frontanbau"],
          ["rear", "Heckanbau"],
          ["towed", "Gezogen"]
        ]
      ],
      ["work_offset_m", "Arbeitsversatz (m)", "number", false, "", 0]
    ]
  }
};

async function request(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers
    }
  });

  const text = await response.text();
  let data = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    const detail = data && typeof data === "object"
      ? data.detail || JSON.stringify(data)
      : data;

    throw new Error(detail || `HTTP ${response.status}`);
  }

  return data;
}

function notice(message, type = "success") {
  const element = $("notice");
  element.textContent = message;
  element.classList.remove("hidden", "error");

  if (type === "error") {
    element.classList.add("error");
  }

  if (type === "success") {
    element.classList.remove("error");
  }
}

function clearNotice() {
  $("notice").textContent = "";
  $("notice").classList.add("hidden");
  $("notice").classList.remove("error");
}

function makeInput(field, value) {
  const [key, label, type, required] = field;
  const id = "input-" + key;

  if (type === "json") {
    const formatted = typeof value === "string"
      ? value
      : JSON.stringify(
          value ?? (key === "reference_line" ? [] : null),
          null,
          2
        );

    return `
      <label>
        ${label}
        <textarea id="${id}" rows="5"
          ${required ? "required" : ""}>${escapeHTML(formatted)}</textarea>
      </label>`;
  }

  if (type === "select") {
    const options = field[6] || [];

    return `
      <label>
        ${label}
        <select id="${id}" ${required ? "required" : ""}>
          ${options.map(([optionValue, optionLabel]) => `
            <option
              value="${escapeHTML(optionValue)}"
              ${String(value ?? "") === String(optionValue)
                ? "selected"
                : ""}
            >${escapeHTML(optionLabel)}</option>
          `).join("")}
        </select>
      </label>`;
  }

  return `
    <label>
      ${label}
      <input
        id="${id}"
        type="${type === "number" ? "number" : "text"}"
        ${type === "number" ? 'step="any"' : ""}
        value="${escapeHTML(value ?? "")}"
        ${required ? "required" : ""}
      >
    </label>`;
}

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

function getSectionFor(type) {
  return type === "tractors"
    ? "tractors"
    : type === "implements"
      ? "implements"
      : type === "fields"
        ? "fields"
        : "dashboard";
}

async function loadAll() {
  try {
    const [fields, tractors, implementsList] = await Promise.all([
      request("/api/fields"),
      request("/api/tractors"),
      request("/api/implements")
    ]);

    $("count-fields").textContent = fields.length;
    $("count-tractors").textContent = tractors.length;
    $("count-implements").textContent = implementsList.length;

    if (current === "fields" || current === "tractors" ||
        current === "implements") {
      const config = configs[current];

      records = current === "fields"
        ? fields
        : current === "tractors"
          ? tractors
          : implementsList;

      renderRecords(config);
    }

    $("connection-status").textContent = "Verbunden";
    $("dashboard-work-status").textContent = "Daten erfolgreich geladen.";
  } catch (error) {
    $("connection-status").textContent = "Verbindungsfehler";
    notice("Daten konnten nicht geladen werden: " + error.message, "error");
  }
}

function renderRecords(config) {
  const container = $(current + "-list") || $("records-list");

  if (!container) return;

  if (!records.length) {
    container.innerHTML = '<article class="panel">Noch keine Einträge vorhanden.</article>';
    return;
  }

  container.innerHTML = records.map(record => {
    const details = current === "fields"
      ? `${(Number(record.area_ha || 0)).toLocaleString("de-DE", {
          minimumFractionDigits: 3,
          maximumFractionDigits: 3
        })} ha`
      : current === "implements"
        ? `Arbeitsbreite: ${escapeHTML(record.working_width_m ?? "–")} m`
        : "Traktor";

    return `
      <article class="record-card">
        <div>
          <h3>${escapeHTML(record.name)}</h3>
          <p>${details}</p>
        </div>
        <div class="record-actions">
          <button data-edit="${record.id}">Bearbeiten</button>
          <button class="danger" data-delete="${record.id}">Löschen</button>
        </div>
      </article>`;
  }).join("");

  container.querySelectorAll("[data-edit]").forEach(button => {
    button.addEventListener("click", () => openEditor(Number(button.dataset.edit)));
  });

  container.querySelectorAll("[data-delete]").forEach(button => {
    button.addEventListener("click", () => removeRecord(Number(button.dataset.delete)));
  });
}

function openEditor(id = null) {
  editingId = id;

  const record = id === null
    ? null
    : records.find(item => Number(item.id) === id);

  if (id !== null && !record) {
    notice("Eintrag nicht gefunden.", "error");
    return;
  }

  const config = configs[current];
  if (!config) return;

  $("editor-title").textContent =
    (id === null ? "Neu anlegen: " : "Bearbeiten: ") + config.title;

  $("form-fields").innerHTML = config.fields.map(field => {
    const key = field[0];
    let value = record ? record[key] : field[5];

    if (value === undefined || value === null) {
      value = key === "reference_line" ? [] : "";
    }

    return makeInput(field, value);
  }).join("");

  const isField = current === "fields";
  $("field-map-container").classList.toggle("hidden", !isField);
  $("editor").classList.remove("hidden");

  if (isField) {
    initFieldMap(record);
  }

  $("editor").scrollIntoView({ behavior: "smooth", block: "start" });
}

function closeEditor() {
  editingId = null;
  $("editor").classList.add("hidden");
  $("field-map-container").classList.add("hidden");
  $("record-form").reset();
}

async function saveRecord(event) {
  event.preventDefault();
  clearNotice();

  const config = configs[current];
  const payload = {};

  try {
    for (const field of config.fields) {
      const [key, label, type, required] = field;
      const input = $("input-" + key);
      const raw = input.value.trim();

      if (required && !raw) {
        throw new Error(`Bitte '${label}' ausfüllen.`);
      }

      if (type === "json") {
        try {
          payload[key] = JSON.parse(raw || (key === "reference_line" ? "[]" : "null"));
        } catch {
          throw new Error(`Ungültiges JSON bei '${label}'.`);
        }
      } else if (type === "number") {
        payload[key] = raw === "" && !required ? null : Number(raw);

        if (payload[key] !== null && !Number.isFinite(payload[key])) {
          throw new Error(`Ungültige Zahl bei '${label}'.`);
        }
      } else {
        payload[key] = raw;
      }
    }

    $("save-button").disabled = true;
    $("save-button").textContent = "Speichert …";

    const url = config.api + (editingId === null ? "" : "/" + editingId);
    const result = await request(url, {
      method: editingId === null ? "POST" : "PUT",
      body: JSON.stringify(payload)
    });

    closeEditor();

    if (current === "fields") {
      notice(`Feld '${result.name}' gespeichert. Fläche: ${
        (Number(result.area_m2) / 10000).toLocaleString("de-DE", {
          minimumFractionDigits: 3,
          maximumFractionDigits: 3
        })
      } ha.`);
    } else {
      notice(config.title + " erfolgreich gespeichert.");
    }

    await loadAll();
  } catch (error) {
    notice("Speichern fehlgeschlagen: " + error.message, "error");
  } finally {
    $("save-button").disabled = false;
    $("save-button").textContent = "Speichern";
  }
}

async function removeRecord(id) {
  const record = records.find(item => Number(item.id) === id);
  if (!record) return;

  if (!confirm(`'${record.name}' wirklich löschen?`)) return;

  try {
    await request(configs[current].api + "/" + id, { method: "DELETE" });
    notice(`'${record.name}' wurde gelöscht.`);
    await loadAll();
  } catch (error) {
    notice("Löschen fehlgeschlagen: " + error.message, "error");
  }
}

function showSection(section) {
  current = section;

  document.querySelectorAll(".page-section").forEach(element => {
    element.classList.toggle("hidden", element.id !== "section-" + section);
  });

  document.querySelectorAll("nav [data-section]").forEach(button => {
    button.classList.toggle("active", button.dataset.section === section);
  });

  closeEditor();
  clearNotice();

  if (configs[section]) {
    loadAll();
  }

  if (section === "work") {
    loadWorkOptions();
    refreshWorkSession();
   
  }

    if (section === "history") {
    loadHistory();
  }
}

document.querySelectorAll("nav [data-section]").forEach(button => {
  button.addEventListener("click", () => showSection(button.dataset.section));
});

document.querySelectorAll("[data-go]").forEach(button => {
  button.addEventListener("click", () => showSection(button.dataset.go));
});

document.querySelectorAll("[data-create]").forEach(button => {
  button.addEventListener("click", () => {
    showSection(button.dataset.create);
    openEditor();
  });
});

$("new-button").addEventListener("click", () => openEditor());
$("cancel-button").addEventListener("click", closeEditor);
$("record-form").addEventListener("submit", saveRecord);

async function initApplication() {
  await loadAll();

  try {
    await loadWorkOptions();
    await refreshWorkSession();
  } catch (error) {
    console.error("Arbeitsgangverwaltung:", error);
  }
}

initApplication();
