
"use strict";

/*
 * pytrac_web/js/work-planning.js
 *
 * Frontend für die Arbeitsplanung.
 *
 * Enthält ausschließlich:
 * - Formularbedienung
 * - Laden vorhandener Stammdaten
 * - API-Aufrufe
 * - Entgegennahme von Kartenklicks
 * - Darstellung der Backend-Ergebnisse
 *
 * Keine fachlichen Berechnungen und keine Geometrieverarbeitung.
 */

const WORK_PLANNING_API = {
  fields: "/api/fields",
  tractors: "/api/tractors",
  implements: "/api/implements",
  preview: "/api/work-plannings/preview",
  save: "/api/work-plannings",
  mapSelection: "/api/work-plannings/map-selection",
};

const workPlanningState = {
  fields: [],
  tractors: [],
  implements: [],
  selectionMode: null,
  selectedStartPoint: null,
  selectedAlignmentBoundary: null,
  selectedStartBoundaryA: null,
  selectedStartBoundaryB: null,
  mapClickHandler: null,
};


/* ---------------------------------------------------------
 * Allgemeine Hilfsfunktionen für die Oberfläche
 * --------------------------------------------------------- */

function workPlanningElement(id) {
  return typeof $ === "function"
    ? $(id)
    : document.getElementById(id);
}


function setWorkPlanningStatus(message, isError = false) {
  const element = workPlanningElement("work-planning-status");

  if (!element) {
    return;
  }

  element.textContent = message;
  element.classList.toggle("error", isError);
  element.setAttribute(
    "role",
    isError ? "alert" : "status",
  );
}


async function workPlanningRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    let message = `Anfrage fehlgeschlagen (${response.status}).`;

    try {
      const body = await response.json();

      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map(item => item.msg || JSON.stringify(item))
          .join("; ");
      }
    } catch {
      // Keine JSON-Fehlermeldung vorhanden.
    }

    throw new Error(message);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}


function populateWorkPlanningSelect(id, records, placeholder) {
  const select = workPlanningElement(id);

  if (!select) {
    return;
  }

  const previousValue = select.value;

  select.replaceChildren();

  const placeholderOption = document.createElement("option");
  placeholderOption.value = "";
  placeholderOption.textContent = placeholder;
  select.appendChild(placeholderOption);

  for (const record of records) {
    const option = document.createElement("option");

    option.value = String(record.id);
    option.textContent = record.name ?? String(record.id);

    select.appendChild(option);
  }

  if (
    previousValue &&
    records.some(record => String(record.id) === previousValue)
  ) {
    select.value = previousValue;
  }
}


/* ---------------------------------------------------------
 * Stammdaten
 * --------------------------------------------------------- */

async function loadWorkPlanningOptions() {
  const [fields, tractors, implementsList] = await Promise.all([
    workPlanningRequest(WORK_PLANNING_API.fields),
    workPlanningRequest(WORK_PLANNING_API.tractors),
    workPlanningRequest(WORK_PLANNING_API.implements),
  ]);

  workPlanningState.fields = fields;
  workPlanningState.tractors = tractors;
  workPlanningState.implements = implementsList;

  populateWorkPlanningSelect(
    "work-planning-field",
    fields,
    "Feld auswählen",
  );

  populateWorkPlanningSelect(
    "work-planning-tractor",
    tractors,
    "Traktor auswählen",
  );

  populateWorkPlanningSelect(
    "work-planning-implement",
    implementsList,
    "Anbaugerät auswählen",
  );
}


/* ---------------------------------------------------------
 * Formulardaten
 * --------------------------------------------------------- */

function getWorkPlanningFormData() {
  const name =
    workPlanningElement("work-planning-name")?.value.trim();

  const tractorId =
    workPlanningElement("work-planning-tractor")?.value;

  const implementId =
    workPlanningElement("work-planning-implement")?.value;

  const fieldId =
    workPlanningElement("work-planning-field")?.value;

  const turnType =
    workPlanningElement("work-planning-turn-type")?.value;

  const headlandMode =
    workPlanningElement("work-planning-headland-mode")?.value;

  const bedWorking = Boolean(
    workPlanningElement("work-planning-bed-working")?.checked,
  );

  const speedInput =
    workPlanningElement("work-planning-speed")?.value.trim();

  const widthsInput =
    workPlanningElement("work-planning-headland-widths")?.value.trim();

  if (!name || !tractorId || !implementId || !fieldId) {
    throw new Error(
      "Bitte Bezeichnung, Traktor, Anbaugerät und Feld angeben.",
    );
  }

  if (
    !workPlanningState.selectedAlignmentBoundary ||
    !workPlanningState.selectedStartBoundaryA ||
    !workPlanningState.selectedStartBoundaryB
  ) {
    throw new Error(
      "Bitte Ausrichtungskante und beide Startgrenzen auswählen.",
    );
  }

  const payload = {
    name,
    tractor_id: Number(tractorId),
    implement_id: Number(implementId),
    field_id: Number(fieldId),
    turn_type: turnType,
    headland_mode: headlandMode,
    bed_working: bedWorking,

    alignment_boundary_id:
      workPlanningState.selectedAlignmentBoundary.id,

    start_boundary_a_id:
      workPlanningState.selectedStartBoundaryA.id,

    start_boundary_b_id:
      workPlanningState.selectedStartBoundaryB.id,
  };

  if (speedInput !== "") {
    payload.speed = Number(speedInput);
  } else {
    payload.speed = null;
  }

  if (widthsInput !== "") {
    payload.headland_working_widths = Number(widthsInput);
  }

  if (workPlanningState.selectedStartPoint) {
    payload.start_point = workPlanningState.selectedStartPoint;
  }

  return payload;
}


/* ---------------------------------------------------------
 * Vorschau und Speichern
 * --------------------------------------------------------- */

async function previewWorkPlanning() {
  try {
    setWorkPlanningStatus("Fordere Planungsvorschau an …");

    const payload = getWorkPlanningFormData();

    const result = await workPlanningRequest(
      WORK_PLANNING_API.preview,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );

    const widthsInput =
      workPlanningElement("work-planning-headland-widths");

    if (widthsInput) {
      widthsInput.value = result.headland_working_widths ?? "";
    }

    renderWorkPlanningPreview(result);

    setWorkPlanningStatus(
      "Planungsvorschau vom Backend erhalten.",
    );
  } catch (error) {
    setWorkPlanningStatus(error.message, true);
  }
}


function renderWorkPlanningPreview(result) {
  const container =
    workPlanningElement("work-planning-preview-result");

  if (!container) {
    return;
  }

  container.replaceChildren();

  const entries = [
    ["Traktorlänge", result.tractor_length, "m"],
    ["Anbaugerätelänge", result.implement_length, "m"],
    ["Arbeitsbreite", result.working_width, "m"],
    [
      "Standard-Vorgewende",
      result.default_headland_working_widths,
      "Arbeitsbreiten",
    ],
    [
      "Gewählte Arbeitsbreiten",
      result.headland_working_widths,
      "Arbeitsbreiten",
    ],
  ];

  for (const [label, value, unit] of entries) {
    if (value === undefined || value === null) {
      continue;
    }

    const row = document.createElement("p");
    const strong = document.createElement("strong");

    strong.textContent = `${label}: `;
    row.append(
      strong,
      document.createTextNode(`${value} ${unit}`),
    );

    container.appendChild(row);
  }
}


async function saveWorkPlanning() {
  try {
    setWorkPlanningStatus("Speichere Arbeitsplanung …");

    const payload = getWorkPlanningFormData();

    const result = await workPlanningRequest(
      WORK_PLANNING_API.save,
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    );

    setWorkPlanningStatus(
      `Arbeitsplanung gespeichert. ID: ${result.id}; ` +
      `Zeitpunkt: ${result.created_at}.`,
    );

    document.dispatchEvent(
      new CustomEvent("pytrac:work-planning-saved", {
        detail: result,
      }),
    );
  } catch (error) {
    setWorkPlanningStatus(error.message, true);
  }
}


/* ---------------------------------------------------------
 * Kartenauswahl
 * --------------------------------------------------------- */

function startWorkPlanningMapSelection(mode) {
  if (
    typeof fieldMap === "undefined" ||
    !fieldMap ||
    typeof fieldMap.on !== "function"
  ) {
    setWorkPlanningStatus(
      "Die vorhandene Feldkarte ist nicht verfügbar.",
      true,
    );
    return;
  }

  stopWorkPlanningMapSelection();

  workPlanningState.selectionMode = mode;

  const labels = {
    start_point: "Startpunkt",
    alignment: "Ausrichtungskante",
    start_boundary_a: "erste Startgrenze",
    start_boundary_b: "zweite Startgrenze",
  };

  setWorkPlanningStatus(
    `Bitte ${labels[mode] ?? "Auswahl"} auf der Karte anklicken.`,
  );

  workPlanningState.mapClickHandler = async event => {
    try {
      if (!event?.latlng) {
        throw new Error("Der Kartenklick enthält keine Koordinaten.");
      }

      const fieldId =
        workPlanningElement("work-planning-field")?.value;

      if (!fieldId) {
        throw new Error("Bitte zuerst ein Feld auswählen.");
      }

      /*
       * Das Frontend übermittelt nur den Modus, die Feld-ID
       * und die angeklickten Koordinaten.
       *
       * Das Backend identifiziert die Grenze beziehungsweise
       * interpretiert den Startpunkt.
       */
      const result = await workPlanningRequest(
        WORK_PLANNING_API.mapSelection,
        {
          method: "POST",
          body: JSON.stringify({
            field_id: Number(fieldId),
            selection_mode: mode,
            coordinates: {
              latitude: event.latlng.lat,
              longitude: event.latlng.lng,
            },
          }),
        },
      );

      applyWorkPlanningMapSelection(mode, result);

      setWorkPlanningStatus(
        result.message ?? "Kartenauswahl übernommen.",
      );
    } catch (error) {
      setWorkPlanningStatus(error.message, true);
    } finally {
      stopWorkPlanningMapSelection();
    }
  };

  fieldMap.on(
    "click",
    workPlanningState.mapClickHandler,
  );
}


function stopWorkPlanningMapSelection() {
  if (
    workPlanningState.mapClickHandler &&
    typeof fieldMap !== "undefined" &&
    fieldMap
  ) {
    fieldMap.off(
      "click",
      workPlanningState.mapClickHandler,
    );
  }

  workPlanningState.mapClickHandler = null;
  workPlanningState.selectionMode = null;
}


function applyWorkPlanningMapSelection(mode, result) {
  /*
   * Die zurückgegebene Grenz-ID kommt vom Backend.
   * Das Frontend berechnet oder interpretiert keine Geometrie.
   */
  switch (mode) {
    case "start_point":
      workPlanningState.selectedStartPoint =
        result.start_point ?? result.coordinates;
      break;

    case "alignment":
      workPlanningState.selectedAlignmentBoundary =
        result.boundary;
      break;

    case "start_boundary_a":
      workPlanningState.selectedStartBoundaryA =
        result.boundary;
      break;

    case "start_boundary_b":
      workPlanningState.selectedStartBoundaryB =
        result.boundary;
      break;
  }

  document.dispatchEvent(
    new CustomEvent("pytrac:work-planning-map-selection", {
      detail: {
        mode,
        result,
      },
    }),
  );
}


/* ---------------------------------------------------------
 * Benutzeroberfläche
 * --------------------------------------------------------- */

function updateWorkPlanningOptions() {
  const turnType =
    workPlanningElement("work-planning-turn-type")?.value;

  const container =
    workPlanningElement("work-planning-bed-working-container");

  const checkbox =
    workPlanningElement("work-planning-bed-working");

  const enabled = turnType === "u_turn";

  if (container) {
    container.hidden = !enabled;
  }

  if (checkbox && !enabled) {
    checkbox.checked = false;
  }
}


function initWorkPlanning() {
  if (!workPlanningElement("work-planning-form")) {
    return;
  }

  workPlanningElement("work-planning-form")
    .addEventListener("submit", event => {
      event.preventDefault();
      previewWorkPlanning();
    });

  workPlanningElement("work-planning-save")
    ?.addEventListener("click", saveWorkPlanning);

  workPlanningElement("work-planning-preview")
    ?.addEventListener("click", previewWorkPlanning);

  workPlanningElement("work-planning-turn-type")
    ?.addEventListener("change", updateWorkPlanningOptions);

  const selectionButtons = {
    "work-planning-select-start-point": "start_point",
    "work-planning-select-alignment": "alignment",
    "work-planning-select-start-boundary-a": "start_boundary_a",
    "work-planning-select-start-boundary-b": "start_boundary_b",
  };

  for (const [elementId, mode] of Object.entries(selectionButtons)) {
    workPlanningElement(elementId)?.addEventListener(
      "click",
      () => startWorkPlanningMapSelection(mode),
    );
  }

  workPlanningElement("work-planning-cancel-selection")
    ?.addEventListener("click", stopWorkPlanningMapSelection);

  workPlanningElement("work-planning-field")
    ?.addEventListener("change", () => {
      workPlanningState.selectedStartPoint = null;
      workPlanningState.selectedAlignmentBoundary = null;
      workPlanningState.selectedStartBoundaryA = null;
      workPlanningState.selectedStartBoundaryB = null;
    });

  updateWorkPlanningOptions();

  loadWorkPlanningOptions().catch(error => {
    setWorkPlanningStatus(
      `Stammdaten konnten nicht geladen werden: ${error.message}`,
      true,
    );
  });
}


if (document.readyState === "loading") {
  document.addEventListener(
    "DOMContentLoaded",
    initWorkPlanning,
    { once: true },
  );
} else {
  initWorkPlanning();
}
