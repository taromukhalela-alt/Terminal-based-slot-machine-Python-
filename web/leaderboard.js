const statusEl = document.getElementById("leaderboard-status");
const bodyEl = document.getElementById("leaderboard-body");
const emptyStateEl = document.getElementById("empty-state");
const frequencyStatusEl = document.getElementById("frequency-status");
const frequencyBodyEl = document.getElementById("frequency-body");
const frequencyEmptyStateEl = document.getElementById("frequency-empty-state");

const state = {
  tier: "A",
};

function currency(value) {
  return `R${value}`;
}

function formatMultiplier(value) {
  return `${Number(value).toFixed(2).replace(/\.00$/, "")}x`;
}

function formatPercent(value) {
  return `${(Number(value) * 100).toFixed(1)}%`;
}

async function requestJson(url) {
  const response = await fetch(url, { credentials: "same-origin" });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Something went wrong.");
  }
  return payload;
}

function renderRows(results) {
  bodyEl.innerHTML = "";
  emptyStateEl.classList.toggle("is-hidden", results.length > 0);

  for (const row of results) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.rank}</td>
      <td>${row.displayName || row.username}</td>
      <td>${formatMultiplier(row.luckMultiplier)}</td>
      <td>${currency(row.winAmount)}</td>
    `;
    bodyEl.appendChild(tr);
  }
}

function renderFrequencyRows(results) {
  frequencyBodyEl.innerHTML = "";
  frequencyEmptyStateEl.classList.toggle("is-hidden", results.length > 0);

  for (const row of results) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.rank}</td>
      <td>${row.displayName || row.username}</td>
      <td>${row.luckyRollCount} / ${row.totalSpins}</td>
      <td>${formatPercent(row.hitRate)}</td>
      <td>${currency(row.bestWin)}</td>
    `;
    frequencyBodyEl.appendChild(tr);
  }
}

async function loadLeaderboard() {
  statusEl.textContent = `Loading Tier ${state.tier}...`;
  frequencyStatusEl.textContent = `Loading Tier ${state.tier} consistency...`;
  try {
    const payload = await requestJson(`/api/leaderboard?tier=${state.tier}`);
    renderRows(payload.topSpins);
    renderFrequencyRows(payload.frequentWinners);
    statusEl.textContent = `Showing Tier ${payload.tier} top 100 single-spin results`;
    frequencyStatusEl.textContent = `Showing Tier ${payload.tier} top 100 frequent winners`;
  } catch (error) {
    statusEl.textContent = error.message;
    frequencyStatusEl.textContent = error.message;
  }
}

document.querySelectorAll("[data-tier]").forEach((button) => {
  button.addEventListener("click", () => {
    state.tier = button.dataset.tier;
    document.querySelectorAll("[data-tier]").forEach((candidate) => {
      candidate.classList.toggle("is-active", candidate === button);
    });
    loadLeaderboard();
  });
});

loadLeaderboard();
