const reelsEl = document.getElementById("reels");
const reelTemplate = document.getElementById("reel-template");
const symbolTemplate = document.getElementById("symbol-template");

const balanceEl = document.getElementById("balance");
const spinTotalEl = document.getElementById("spin-total");
const lastWinEl = document.getElementById("last-win");
const lastNetEl = document.getElementById("last-net");
const winningLinesEl = document.getElementById("winning-lines");
const statusPillEl = document.getElementById("status-pill");
const depositTierEl = document.getElementById("deposit-tier");
const totalDepositEl = document.getElementById("total-deposit");

const authTitleEl = document.getElementById("auth-title");
const guestAuthEl = document.getElementById("guest-auth");
const userPanelEl = document.getElementById("user-panel");
const usernameDisplayEl = document.getElementById("username-display");
const tierDisplayEl = document.getElementById("tier-display");
const topTenDisplayEl = document.getElementById("top-ten-display");
const authFormEl = document.getElementById("auth-form");
const authSubmitEl = document.getElementById("auth-submit");
const usernameInputEl = document.getElementById("username-input");
const passwordInputEl = document.getElementById("password-input");
const logoutButtonEl = document.getElementById("logout-button");

const depositInput = document.getElementById("deposit-input");
const depositButton = document.getElementById("deposit-button");
const spinButton = document.getElementById("spin-button");
const betValueEl = document.getElementById("bet-value");

const symbols = ["A", "B", "C", "D"];

const state = {
  authMode: "login",
  authenticated: false,
  user: null,
  balance: 0,
  bet: 10,
  limits: {
    minBet: 1,
    maxBet: 300,
    maxLines: 3,
    maxDeposit: 3000,
  },
  reels: [],
  isSpinning: false,
};

function randSymbol() {
  return symbols[Math.floor(Math.random() * symbols.length)];
}

function currency(value) {
  return `R${value}`;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function formatTier(tier) {
  const labels = {
    A: "Tier A",
    B: "Tier B",
    C: "Tier C",
  };
  return labels[tier] || "Guest";
}

function createSymbolCard(symbol) {
  const node = symbolTemplate.content.firstElementChild.cloneNode(true);
  node.dataset.symbol = symbol;
  node.querySelector("span").textContent = symbol;
  return node;
}

function setTrackToColumns(track, symbolsForColumn, winningLines = []) {
  track.innerHTML = "";
  const cards = symbolsForColumn.map((symbol, rowIndex) => {
    const card = createSymbolCard(symbol);
    card.classList.toggle("is-winning", winningLines.includes(rowIndex + 1));
    track.appendChild(card);
    return card;
  });
  track.style.transition = "none";
  track.style.transform = "translateY(0)";
  return cards;
}

function createReels() {
  for (let i = 0; i < 3; i += 1) {
    const reel = reelTemplate.content.firstElementChild.cloneNode(true);
    const track = reel.querySelector(".reel__symbols");
    const cards = setTrackToColumns(track, ["A", "A", "A"]);

    reelsEl.appendChild(reel);
    state.reels.push({ reel, track, cards });
  }
}

function renderAuthMode() {
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.authMode === state.authMode);
  });
  authSubmitEl.textContent = state.authMode === "login" ? "Login" : "Create account";
  passwordInputEl.autocomplete = state.authMode === "login" ? "current-password" : "new-password";
}

function updateControls() {
  const activeLines = state.limits.maxLines;
  const maxBetForRound = state.balance > 0 ? Math.min(state.limits.maxBet, Math.floor(state.balance / activeLines)) : 0;
  state.bet = maxBetForRound <= 0 ? state.limits.minBet : clamp(state.bet, state.limits.minBet, maxBetForRound);

  betValueEl.textContent = state.bet;
  balanceEl.textContent = currency(state.balance);
  spinTotalEl.textContent = currency(activeLines * state.bet);
  totalDepositEl.textContent = currency(state.user?.totalDeposit ?? 0);
  depositTierEl.textContent = formatTier(state.user?.depositTier);

  depositInput.max = String(state.limits.maxDeposit ?? 3000);

  const canSpin =
    state.authenticated &&
    !state.isSpinning &&
    state.balance >= activeLines * state.limits.minBet &&
    activeLines * state.bet <= state.balance;

  spinButton.disabled = !canSpin;
  depositButton.disabled = !state.authenticated;
  depositInput.disabled = !state.authenticated;
}

function renderResult(data) {
  lastWinEl.textContent = currency(data.lastWin ?? 0);
  lastNetEl.textContent = currency(data.lastNet ?? 0);
  winningLinesEl.textContent = data.winningLines?.length ? data.winningLines.join(", ") : "-";
  statusPillEl.textContent = data.status;
}

function renderAccount() {
  const isAuthenticated = state.authenticated && state.user;
  guestAuthEl.classList.toggle("is-hidden", isAuthenticated);
  userPanelEl.classList.toggle("is-hidden", !isAuthenticated);
  authTitleEl.textContent = isAuthenticated ? "Account ready" : "Sign in to play";

  if (isAuthenticated) {
    usernameDisplayEl.textContent = state.user.displayName || state.user.username;
    tierDisplayEl.textContent = formatTier(state.user.depositTier);
    topTenDisplayEl.textContent = state.user.isTopTen ? "Unlocked" : "Locked";
  }
}

function applySnapshot(data) {
  state.authenticated = data.authenticated;
  state.user = data.user;
  state.balance = data.balance;
  state.limits = data.limits;
  renderResult(data);
  paintFinalGrid(data.lastSpin, data.winningLines);
  renderAccount();
  updateControls();
}

function paintFinalGrid(columns, winningLines = []) {
  state.reels.forEach((reelState, columnIndex) => {
    reelState.cards = setTrackToColumns(reelState.track, columns[columnIndex], winningLines);
  });
}

function animateSpin(finalColumns, winningLines) {
  state.isSpinning = true;
  updateControls();

  state.reels.forEach((reelState, columnIndex) => {
    const previewSymbols = [];
    for (let i = 0; i < 12; i += 1) {
      previewSymbols.push(randSymbol());
    }
    previewSymbols.push(...finalColumns[columnIndex]);

    reelState.track.innerHTML = "";
    const animatedCards = previewSymbols.map((symbol) => {
      const card = createSymbolCard(symbol);
      reelState.track.appendChild(card);
      return card;
    });

    reelState.track.style.transition = "none";
    reelState.track.style.transform = "translateY(0)";

    requestAnimationFrame(() => {
      const cardHeight = animatedCards[0].getBoundingClientRect().height + 14;
      const distance = (previewSymbols.length - 3) * cardHeight;
      reelState.track.style.transition = `transform ${820 + columnIndex * 180}ms cubic-bezier(0.2, 0.82, 0.2, 1)`;
      reelState.track.style.transform = `translateY(-${distance}px)`;
    });
  });

  window.setTimeout(() => {
    paintFinalGrid(finalColumns, winningLines);
    state.isSpinning = false;
    updateControls();
  }, 1280);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    credentials: "same-origin",
    ...options,
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Something went wrong.");
  }
  return payload;
}

async function refreshState() {
  const data = await requestJson("/api/state");
  applySnapshot(data);
}

async function deposit() {
  const amount = Number.parseInt(depositInput.value, 10);
  try {
    const data = await requestJson("/api/deposit", {
      method: "POST",
      body: JSON.stringify({ amount }),
    });
    applySnapshot(data);
    depositInput.value = "";
  } catch (error) {
    statusPillEl.textContent = error.message;
  }
}

async function spin() {
  if (state.isSpinning || !state.authenticated) {
    return;
  }

  statusPillEl.textContent = "Spinning reels...";
  try {
    const data = await requestJson("/api/spin", {
      method: "POST",
      body: JSON.stringify({
        bet: state.bet,
      }),
    });
    state.authenticated = data.authenticated;
    state.user = data.user;
    state.balance = data.balance;
    state.limits = data.limits;
    renderResult(data);
    renderAccount();
    animateSpin(data.lastSpin, data.winningLines || []);
  } catch (error) {
    statusPillEl.textContent = error.message;
  }
}

async function submitAuth(event) {
  event.preventDefault();
  try {
    const payload = await requestJson(`/api/${state.authMode}`, {
      method: "POST",
      body: JSON.stringify({
        username: usernameInputEl.value.trim(),
        password: passwordInputEl.value,
      }),
    });
    usernameInputEl.value = "";
    passwordInputEl.value = "";
    applySnapshot(payload);
  } catch (error) {
    statusPillEl.textContent = error.message;
  }
}

async function logout() {
  try {
    await requestJson("/api/logout", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await refreshState();
  } catch (error) {
    statusPillEl.textContent = error.message;
  }
}

document.querySelectorAll("[data-auth-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.authMode = button.dataset.authMode;
    renderAuthMode();
  });
});

document.querySelectorAll("[data-adjust]").forEach((button) => {
  button.addEventListener("click", () => {
    const delta = Number.parseInt(button.dataset.delta, 10);
    state.bet = clamp(state.bet + delta, state.limits.minBet, state.limits.maxBet);
    updateControls();
  });
});

authFormEl.addEventListener("submit", submitAuth);
logoutButtonEl.addEventListener("click", logout);
depositButton.addEventListener("click", deposit);
spinButton.addEventListener("click", spin);

createReels();
renderAuthMode();
refreshState().catch((error) => {
  statusPillEl.textContent = error.message;
});
