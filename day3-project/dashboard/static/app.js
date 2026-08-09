const form = document.querySelector("#query-form");
const submitButton = document.querySelector("#submit-button");
const formError = document.querySelector("#form-error");
const resultTitle = document.querySelector("#result-title");
const resultDate = document.querySelector("#result-date");
const resultBody = document.querySelector("#result-body");
const historyList = document.querySelector("#history-list");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderResult(item) {
  resultTitle.textContent = item.location;
  resultDate.textContent = item.date;
  resultBody.className = "result-body";
  resultBody.innerHTML = `
    <div class="recommendation">
      <div>
        <div class="recommendation-title">${escapeHtml(item.recommendation)}</div>
        <p class="recommendation-copy">${escapeHtml(item.conditions)} with a forecast high of ${escapeHtml(item.temperature_high_f)} F and low of ${escapeHtml(item.temperature_low_f)} F. The adapter applied its documented threshold rule.</p>
      </div>
      <div class="signal"><span class="signal-label">Forecast signal</span><span class="signal-value">${escapeHtml(item.precipitation_probability_pct)}% rain</span></div>
    </div>
    <div class="metric-strip">
      <div class="metric"><span class="metric-label">Precipitation</span><span class="metric-value">${escapeHtml(item.precipitation_mm)} mm</span></div>
      <div class="metric"><span class="metric-label">Max gusts</span><span class="metric-value">${escapeHtml(item.wind_gusts_mph)} mph</span></div>
      <div class="metric"><span class="metric-label">Conditions</span><span class="metric-value">${escapeHtml(item.conditions)}</span></div>
      <div class="metric"><span class="metric-label">Decision</span><span class="metric-value">${item.bring_umbrella ? "Umbrella" : "Optional"}</span></div>
    </div>`;
}

function renderHistory(items) {
  if (!items.length) {
    historyList.innerHTML = '<div class="history-empty">No recent queries. Your first result will appear here.</div>';
    return;
  }
  historyList.innerHTML = items.map((item) => `
    <article class="history-item">
      <div class="history-item-top"><span>${escapeHtml(item.date)}</span><span>${escapeHtml(item.created_at)}</span></div>
      <div class="history-location">${escapeHtml(item.location)}</div>
      <div class="history-recommendation">${escapeHtml(item.recommendation)}</div>
      <div class="history-metrics">${escapeHtml(item.conditions)} · ${escapeHtml(item.precipitation_probability_pct)}% rain</div>
    </article>`).join("");
}

async function loadHistory() {
  const response = await fetch("/api/history");
  const data = await response.json();
  renderHistory(data.items || []);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.hidden = true;
  submitButton.disabled = true;
  resultBody.className = "result-body";
  resultBody.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton short"></div>';
  resultTitle.textContent = "Loading forecast";
  resultDate.textContent = "";
  const formData = new FormData(form);
  const body = {
    location: formData.get("location"),
    date: formData.get("date") || null,
    question: formData.get("question") || null,
  };
  try {
    const response = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "The prediction could not be completed.");
    renderResult(data);
    await loadHistory();
  } catch (error) {
    resultTitle.textContent = "No prediction yet";
    resultDate.textContent = "";
    resultBody.className = "result-body empty-state";
    resultBody.innerHTML = '<p>The forecast could not be loaded. Check the error below and try again.</p>';
    formError.textContent = error.message;
    formError.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
});

loadHistory().catch(() => {
  historyList.innerHTML = '<div class="history-empty">Recent activity is unavailable until the dashboard API responds.</div>';
});
