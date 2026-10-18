"use strict";

let workSessionBusy = false;

function setWorkControls(status) {
  const idle = status === "idle";
  const running = status === "running";
  const paused = status === "paused";

  $("work-start").disabled = !idle || workSessionBusy;
  $("work-pause").disabled = !running || workSessionBusy;
  $("work-resume").disabled = !paused || workSessionBusy;
  $("work-finish").disabled = idle || workSessionBusy;

  for (const id of [
    "work-name",
    "work-field",
    "work-tractor",
    "work-implement",
    "work-headland"
  ]) {
    $(id).disabled = !idle || workSessionBusy;
  }
}

async function loadWorkOptions() {
  const [fields, tractors, implementsList] = await Promise.all([
    request("/api/fields"),
    request("/api/tractors"),
    request("/api/implements")
  ]);

  function fillSelect(id, items, label) {
    const select = $(id);
    const previous = select.value;

    select.innerHTML = "";

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Bitte auswählen";
    select.appendChild(placeholder);

    for (const item of items) {
      const option = document.createElement("option");
      option.value = String(item.id);
      option.textContent = label(item);
      select.appendChild(option);
    }

    if (items.some(item => String(item.id) === previous)) {
      select.value = previous;
    }
  }

  fillSelect("work-field", fields, item => item.name);
  fillSelect("work-tractor", tractors, item => item.name);
  fillSelect("work-implement", implementsList, item => item.name);
}

async function refreshWorkSession() {
  try {
    const data = await request("/api/work-sessions/current");
    const session = data.session;
    const status = data.status || "idle";

    const labels = {
      idle: "Kein Arbeitsgang aktiv",
      running: "Läuft",
      paused: "Pausiert"
    };

    $("work-status").textContent = labels[status] || status;

    $("work-area").textContent =
      (Number(data.coverage_area_m2 || 0) / 10000)
        .toLocaleString("de-DE", {
          minimumFractionDigits: 3,
          maximumFractionDigits: 3
        }) + " ha";

    const guidance = data.guidance || {};

    $("work-gps").textContent = guidance.gps_valid
      ? "Gültig"
      : "Nicht bestätigt";

    $("work-guidance").textContent = guidance.guidance_valid
      ? "Verfügbar"
      : "Nicht verfügbar";

    $("work-message").textContent = guidance.message || "";

    $("work-session-info").textContent = session
      ? `${session.name} · Feld: ${session.field?.name || "–"} · ` +
        `Traktor: ${session.tractor?.name || "–"} · ` +
        `Anbaugerät: ${session.implement?.name || "–"}`
      : "Aktuell ist kein Arbeitsgang aktiv.";

    $("dashboard-work-status").textContent =
      labels[status] || status;

    setWorkControls(status);
  } catch (error) {
    $("work-message").textContent =
      "Status konnte nicht geladen werden: " + error.message;
  }
}

async function runWorkAction(url, payload = null) {
  if (workSessionBusy) return;

  workSessionBusy = true;

  const statusText = $("work-status").textContent;
  const status = statusText === "Läuft"
    ? "running"
    : statusText === "Pausiert"
      ? "paused"
      : "idle";

  setWorkControls(status);
  $("work-message").textContent = "Bitte warten …";

  try {
    const options = { method: "POST" };

    if (payload !== null) {
      options.body = JSON.stringify(payload);
    }

    const result = await request(url, options);

    $("work-message").textContent =
      result.message || "Aktion erfolgreich.";
  } catch (error) {
    $("work-message").textContent =
      "Aktion fehlgeschlagen: " + error.message;
  } finally {
    workSessionBusy = false;
    await refreshWorkSession();
  }
}

$("work-start").addEventListener("click", async () => {
  const fieldId = Number($("work-field").value);
  const tractorId = Number($("work-tractor").value);
  const implementId = Number($("work-implement").value);
  const headlandDepth = Number($("work-headland").value);
  const name = $("work-name").value.trim();

  if (!fieldId || !tractorId || !implementId) {
    $("work-message").textContent =
      "Bitte Feld, Traktor und Anbaugerät auswählen.";
    return;
  }

  if (
    !name ||
    !Number.isFinite(headlandDepth) ||
    headlandDepth < 0 ||
    headlandDepth > 100
  ) {
    $("work-message").textContent =
      "Bitte Bezeichnung und Vorgewende-Tiefe prüfen.";
    return;
  }

  await runWorkAction("/api/work-sessions", {
    field_id: fieldId,
    tractor_id: tractorId,
    implement_id: implementId,
    name,
    headland_depth_m: headlandDepth
  });
});

$("work-pause").addEventListener("click", () =>
  runWorkAction("/api/work-sessions/pause")
);

$("work-resume").addEventListener("click", () =>
  runWorkAction("/api/work-sessions/resume")
);

$("work-finish").addEventListener("click", () => {
  if (confirm("Möchtest du den Arbeitsgang wirklich beenden?")) {
    runWorkAction("/api/work-sessions/finish");
  }
});

$("work-refresh").addEventListener("click", async () => {
  try {
    await loadWorkOptions();
    await refreshWorkSession();
  } catch (error) {
    $("work-message").textContent =
      "Aktualisierung fehlgeschlagen: " + error.message;
  }
});
