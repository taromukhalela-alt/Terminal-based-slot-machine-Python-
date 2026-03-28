const reelsEl = document.getElementById("reels");
const reelTemplate = document.getElementById("reel-template");
const symbolTemplate = document.getElementById("symbol-template");
const difficultyModalEl = document.getElementById("difficulty-modal");
const difficultyGridEl = document.getElementById("difficulty-grid");
const difficultyEyebrowEl = document.getElementById("difficulty-eyebrow");
const difficultyTitleEl = document.getElementById("difficulty-title");
const difficultyCopyEl = document.getElementById("difficulty-copy");
const difficultyCloseButtonEl = document.getElementById("difficulty-close-button");

const balanceEl = document.getElementById("balance");
const spinTotalEl = document.getElementById("spin-total");
const difficultyLabelEl = document.getElementById("difficulty-label");
const tdaTotalEl = document.getElementById("tda-total");
const aOddsEl = document.getElementById("a-odds");
const winRatioEl = document.getElementById("win-ratio");
const lastWinEl = document.getElementById("last-win");
const lastNetEl = document.getElementById("last-net");
const winningLinesEl = document.getElementById("winning-lines");
const statusPillEl = document.getElementById("status-pill");

const authTitleEl = document.getElementById("auth-title");
const guestAuthEl = document.getElementById("guest-auth");
const userPanelEl = document.getElementById("user-panel");
const usernameDisplayEl = document.getElementById("username-display");
const modeDisplayEl = document.getElementById("mode-display");
const topTenDisplayEl = document.getElementById("top-ten-display");
const authFormEl = document.getElementById("auth-form");
const authSubmitEl = document.getElementById("auth-submit");
const usernameInputEl = document.getElementById("username-input");
const passwordInputEl = document.getElementById("password-input");
const logoutButtonEl = document.getElementById("logout-button");
const chooseModeButtonEl = document.getElementById("choose-mode-button");
const modeResetHintEl = document.getElementById("mode-reset-hint");

const depositInput = document.getElementById("deposit-input");
const depositButton = document.getElementById("deposit-button");
const spinButton = document.getElementById("spin-button");
const betValueEl = document.getElementById("bet-value");
const betTextInputEl = document.getElementById("bet-text-input");
const turboToggleEl = document.getElementById("turbo-toggle");
const easyCapWarningEl = document.getElementById("easy-cap-warning");
const easyCapAmountEl = document.getElementById("easy-cap-amount");

// Vault (TDA) Elements
const vaultTdaEl = document.getElementById("vault-tda");
const vaultPlayBalanceEl = document.getElementById("vault-play-balance");
const vaultClassEl = document.getElementById("vault-class");
const depositToPlayInput = document.getElementById("deposit-to-play-input");
const depositToPlayButton = document.getElementById("deposit-to-play-button");
const depositToPlayHint = document.getElementById("deposit-to-play-hint");
const rechargeSection = document.getElementById("recharge-section");
const rechargeButton = document.getElementById("recharge-button");
const rechargeHint = document.getElementById("recharge-hint");

// Session Stats Elements
const sessionWonEl = document.getElementById("session-won");
const luckiestSpinEl = document.getElementById("luckiest-spin");
const sessionSpinsEl = document.getElementById("session-spins");

// Auto-Spin Elements
const autoSpinStartEl = document.getElementById("auto-spin-start");
const autoSpinStopEl = document.getElementById("auto-spin-stop");
const autoThresholdEl = document.getElementById("auto-threshold");
const autoSpinProgressEl = document.getElementById("auto-spin-progress");
const autoSpinFillEl = document.getElementById("auto-spin-fill");
const autoSpinCountdownEl = document.getElementById("auto-spin-countdown");
const autoSpinStatusEl = document.getElementById("auto-spin-status");

const symbols = ["A", "B", "C", "D"];

const state = {
  authMode: "login",
  authenticated: false,
  user: null,
  tda: null,
  bet: 10,
  reels: [],
  isSpinning: false,
  difficultyOptions: [],
  needsDifficultySelection: false,
  modeChooserOpen: false,
  // New QoL Features
  turboMode: false,
  sessionStats: {
    totalWon: 0,
    luckiestMultiplier: 0,
    spins: 0,
  },
  // Auto-Spin State
  autoSpin: {
    enabled: false,
    count: 0,
    remaining: 0,
    threshold: 5,
    selectedCount: null,
  },
};

function currency(value) {
  return `R${Number(value).toFixed(2).replace(".00", "")}`;
}

function percent(value) {
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function randSymbol() {
  return symbols[Math.floor(Math.random() * symbols.length)];
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

// ================================
// SESSION STATS FUNCTIONS
// ================================

function updateSessionStats(result) {
  if (result.lastWin > 0 && result.bet > 0) {
    const multiplier = result.lastWin / (result.bet * 3);
    
    // Update total won this session
    state.sessionStats.totalWon += result.lastWin;
    sessionWonEl.textContent = currency(state.sessionStats.totalWon);
    sessionWonEl.classList.toggle("positive", state.sessionStats.totalWon > 0);
    sessionWonEl.classList.toggle("negative", state.sessionStats.totalWon < 0);
    
    // Update luckiest spin
    if (multiplier > state.sessionStats.luckiestMultiplier) {
      state.sessionStats.luckiestMultiplier = multiplier;
      luckiestSpinEl.textContent = `${multiplier.toFixed(1)}×`;
    }
    
    // Update session spins
    state.sessionStats.spins++;
    sessionSpinsEl.textContent = state.sessionStats.spins;
  }
}

function resetSessionStats() {
  state.sessionStats = {
    totalWon: 0,
    luckiestMultiplier: 0,
    spins: 0,
  };
  sessionWonEl.textContent = "R0";
  sessionWonEl.classList.remove("positive", "negative");
  luckiestSpinEl.textContent = "-";
  sessionSpinsEl.textContent = "0";
}

// ================================
// TURBO MODE FUNCTIONS
// ================================

function toggleTurboMode() {
  state.turboMode = !state.turboMode;
  turboToggleEl.classList.toggle("is-active", state.turboMode);
  turboToggleEl.setAttribute("aria-pressed", state.turboMode);
  turboToggleEl.querySelector(".turbo-label").textContent = state.turboMode ? "Turbo ON" : "Turbo";
}

// ================================
// AUTO-SPIN FUNCTIONS
// ================================

function selectAutoSpinCount(count) {
  state.autoSpin.selectedCount = count;
  document.querySelectorAll(".auto-spin-count").forEach((btn) => {
    btn.classList.toggle("is-selected", parseInt(btn.dataset.spins, 10) === count);
  });
}

function startAutoSpin() {
  if (!state.authenticated || state.isSpinning) return;
  
  const count = state.autoSpin.selectedCount || 10;
  let threshold = parseFloat(autoThresholdEl.value);
  
  // Validate threshold is a positive number
  if (isNaN(threshold) || threshold < 1) {
    threshold = 5;
    autoThresholdEl.value = "5";
  }
  
  state.autoSpin = {
    enabled: true,
    count: count,
    remaining: count,
    threshold: threshold,
    selectedCount: count,
  };
  
  autoSpinStartEl.style.display = "none";
  autoSpinStopEl.style.display = "block";
  autoSpinProgressEl.style.display = "flex";
  updateAutoSpinProgress();
  
  executeAutoSpin();
}

function stopAutoSpin() {
  state.autoSpin.enabled = false;
  autoSpinStartEl.style.display = "block";
  autoSpinStopEl.style.display = "none";
  autoSpinProgressEl.style.display = "none";
  autoSpinStatusEl.textContent = "Stopped";
}

function updateAutoSpinProgress() {
  const total = state.autoSpin.count;
  const remaining = state.autoSpin.remaining;
  const completed = total - remaining;
  const percent = (completed / total) * 100;
  
  autoSpinFillEl.style.width = `${percent}%`;
  autoSpinCountdownEl.textContent = `${completed}/${total}`;
}

async function executeAutoSpin() {
  if (!state.autoSpin.enabled || state.autoSpin.remaining <= 0) {
    stopAutoSpin();
    statusPillEl.textContent = "Auto-spin completed!";
    return;
  }
  
  if (state.isSpinning || !state.authenticated || state.needsDifficultySelection) {
    // Wait and retry
    await sleep(100);
    if (state.autoSpin.enabled) {
      executeAutoSpin();
    }
    return;
  }
  
  // Check if balance is sufficient
  const balance = state.user?.balance ?? 0;
  if (balance < state.bet * 3) {
    stopAutoSpin();
    statusPillEl.textContent = "Insufficient balance for auto-spin.";
    return;
  }
  
  state.autoSpin.remaining--;
  updateAutoSpinProgress();
  autoSpinStatusEl.textContent = "Spinning...";
  
  try {
    const data = await requestJson("/api/spin", {
      method: "POST",
      body: JSON.stringify({ bet: state.bet }),
    });
    
    state.authenticated = data.authenticated;
    state.user = data.user;
    state.difficultyOptions = data.difficultyOptions || [];
    state.needsDifficultySelection = data.needsDifficultySelection;
    renderResult(data);
    renderAccount();
    renderDifficultyChooser();
    updateSessionStats(data);
    updateControls();
    animateSpin(data.lastSpin, data.winningLines || []);
    
    // Check if threshold reached
    if (data.lastWin > 0 && data.bet > 0) {
      const multiplier = data.lastWin / (data.bet * 3);
      if (multiplier >= state.autoSpin.threshold) {
        stopAutoSpin();
        statusPillEl.textContent = `🎉 Auto-spin stopped! Hit ${multiplier.toFixed(1)}× multiplier!`;
        return;
      }
    }
    
    // Check if session ended (no more spins)
    if (!state.autoSpin.enabled || state.autoSpin.remaining <= 0) {
      stopAutoSpin();
      return;
    }
    
    // Continue auto-spin after animation
    const animDuration = state.turboMode ? 400 : 1400;
    setTimeout(() => {
      if (state.autoSpin.enabled) {
        executeAutoSpin();
      }
    }, animDuration);
    
  } catch (error) {
    statusPillEl.textContent = error.message;
    stopAutoSpin();
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ================================
// VAULT / TDA FUNCTIONS
// ================================

function updateEasyCapWarning() {
  const selectedClass = state.user?.selectedClass || state.user?.difficulty;
  const isEasyMode = selectedClass === "easy";
  const depositCap = state.user?.depositCap;

  if (isEasyMode && depositCap != null) {
    easyCapWarningEl.style.display = "flex";
    easyCapAmountEl.textContent = currency(depositCap);
  } else {
    easyCapWarningEl.style.display = "none";
  }
}

function updateRechargeUI() {
  if (!rechargeSection) return;
  const selectedClass = state.user?.selectedClass || state.user?.difficulty;
  const classConfig = state.user?.classConfig;

  if (!classConfig || !classConfig.bankruptcy_protection) {
    rechargeSection.style.display = "none";
    return;
  }

  rechargeSection.style.display = "block";
  const rechargeAt = state.tda?.rechargeAvailableAt;
  const tda = state.tda?.total ?? 0;
  const floor = classConfig.min_tda_floor ?? 10;

  if (tda > floor) {
    rechargeButton.disabled = true;
    rechargeHint.textContent = "Vault is above bankruptcy threshold. No recharge needed.";
  } else if (rechargeAt) {
    const rechargeDate = new Date(rechargeAt);
    const now = new Date();
    if (now < rechargeDate) {
      rechargeButton.disabled = true;
      const hours = Math.ceil((rechargeDate - now) / (1000 * 60 * 60));
      rechargeHint.textContent = `Recharge available in ~${hours}h (${rechargeDate.toLocaleString()})`;
    } else {
      rechargeButton.disabled = false;
      rechargeHint.textContent = "Recharge available! Click to restore your Vault.";
    }
  } else {
    rechargeButton.disabled = false;
    rechargeHint.textContent = "Recharge available. Click to restore your Vault.";
  }
}

async function depositToPlay() {
  if (!state.authenticated || state.needsDifficultySelection) return;
  const amount = Number.parseFloat(depositToPlayInput?.value);
  if (isNaN(amount) || amount <= 0) {
    statusPillEl.textContent = "Enter a valid amount to deposit to play balance.";
    return;
  }
  try {
    const data = await requestJson("/api/deposit-to-play", {
      method: "POST",
      body: JSON.stringify({ amount }),
    });
    applySnapshot(data);
    if (depositToPlayInput) depositToPlayInput.value = "";
    statusPillEl.textContent = `Moved ${currency(amount)} from Vault to Play Balance.`;
  } catch (error) {
    statusPillEl.textContent = error.message;
  }
}

async function recharge() {
  if (!state.authenticated) return;
  try {
    const data = await requestJson("/api/recharge", {
      method: "POST",
      body: JSON.stringify({}),
    });
    applySnapshot(data);
    if (data.rechargeResult) {
      statusPillEl.textContent = `Vault recharged to ${currency(data.rechargeResult.new_tda)}!`;
    } else {
      statusPillEl.textContent = "Vault recharged!";
    }
  } catch (error) {
    statusPillEl.textContent = error.message;
  }
}

// ================================
// EXISTING FUNCTIONS
// ================================

function renderAuthMode() {
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.authMode === state.authMode);
  });
  authSubmitEl.textContent = state.authMode === "login" ? "Login" : "Create account";
}

function renderAccount() {
  const isAuthenticated = state.authenticated && state.user;
  guestAuthEl.classList.toggle("is-hidden", isAuthenticated);
  userPanelEl.classList.toggle("is-hidden", !isAuthenticated);
  authTitleEl.textContent = isAuthenticated ? "Account ready" : "Sign in to play";

  if (isAuthenticated) {
    usernameDisplayEl.textContent = state.user.displayName || state.user.username;
    modeDisplayEl.textContent = state.user.classLabel || state.user.difficultyLabel || "Unset";
    topTenDisplayEl.textContent = state.user.isTopTen ? "Unlocked" : "Locked";
    const hasMode = state.user.selectedClass || state.user.difficulty;
    chooseModeButtonEl.textContent = hasMode ? "Change class" : "Select class";
    modeResetHintEl.textContent = hasMode
      ? "Changing class resets your Vault (TDA), play balance, run history, and leaderboard score."
      : "Pick a class before you deposit or spin.";
  }
}

function updateControls() {
  const playBalance = state.user?.balance ?? 0;
  const tda = state.tda?.total ?? 0;
  const depositCap = state.user?.depositCap;
  const maxBetPerLine = Math.max(1, Math.floor(playBalance / 3));
  state.bet = clamp(state.bet, 1, maxBetPerLine || 1);
  betValueEl.textContent = state.bet;
  betTextInputEl.value = state.bet;
  betTextInputEl.max = maxBetPerLine || 1;

  // Stats grid
  balanceEl.textContent = currency(playBalance);
  spinTotalEl.textContent = currency(state.bet * 3);
  difficultyLabelEl.textContent = state.user?.classLabel ?? state.user?.difficultyLabel ?? "Unset";
  if (tdaTotalEl) tdaTotalEl.textContent = currency(tda);
  aOddsEl.textContent = state.user?.aOddsText ?? "Choose mode";
  winRatioEl.textContent = percent(state.user?.hitRate ?? 0);

  // Vault display
  if (vaultTdaEl) vaultTdaEl.textContent = currency(tda);
  if (vaultPlayBalanceEl) vaultPlayBalanceEl.textContent = currency(playBalance);
  if (vaultClassEl) vaultClassEl.textContent = state.user?.classLabel ?? "-";

  // Deposit to play hint
  if (depositToPlayHint) {
    const capText = depositCap != null ? ` (cap: ${currency(depositCap)}/transfer)` : " (no cap)";
    depositToPlayHint.textContent = `Vault: ${currency(tda)} available${capText}`;
  }

  // Recharge section
  updateRechargeUI();

  const canSpin =
    state.authenticated &&
    !state.needsDifficultySelection &&
    !state.isSpinning &&
    !state.autoSpin.enabled &&
    playBalance >= state.bet * 3;

  spinButton.disabled = !canSpin;
  depositButton.disabled = !state.authenticated || state.needsDifficultySelection;
  depositInput.disabled = !state.authenticated || state.needsDifficultySelection;
  betTextInputEl.disabled = !state.authenticated || state.needsDifficultySelection;
  if (depositToPlayButton) {
    depositToPlayButton.disabled = !state.authenticated || state.needsDifficultySelection || tda <= 0;
  }

  // Update easy cap warning
  updateEasyCapWarning();
}

function renderResult(data) {
  lastWinEl.textContent = currency(data.lastWin ?? 0);
  lastNetEl.textContent = currency(data.lastNet ?? 0);
  winningLinesEl.textContent = data.winningLines?.length ? data.winningLines.join(", ") : "-";
  statusPillEl.textContent = data.status;
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
      // Turbo mode makes animation faster
      const duration = state.turboMode ? 200 + columnIndex * 50 : 820 + columnIndex * 180;
      reelState.track.style.transition = `transform ${duration}ms cubic-bezier(0.2, 0.82, 0.2, 1)`;
      reelState.track.style.transform = `translateY(-${distance}px)`;
    });
  });

  // Turbo mode makes final reveal faster
  const delay = state.turboMode ? 350 : 1280;
  window.setTimeout(() => {
    paintFinalGrid(finalColumns, winningLines);
    state.isSpinning = false;
    updateControls();
    
    // Continue auto-spin if enabled
    if (state.autoSpin.enabled && state.autoSpin.remaining > 0) {
      setTimeout(() => executeAutoSpin(), 50);
    }
  }, delay);
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

  const contentType = response.headers.get("content-type") || "";
  const rawText = await response.text();
  const looksJson = contentType.includes("application/json") || rawText.trim().startsWith("{") || rawText.trim().startsWith("[");

  let payload = null;
  if (rawText && looksJson) {
    try {
      payload = JSON.parse(rawText);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const apiError = payload && typeof payload === "object" ? payload.error : null;
    const fallback = rawText?.trim()
      ? `Request failed (${response.status}). ${rawText.trim().slice(0, 180)}`
      : `Request failed (${response.status}).`;
    throw new Error(apiError || fallback);
  }

  if (payload === null) {
    throw new Error("Server returned an invalid response (expected JSON).");
  }

  return payload;
}

function renderDifficultyChooser() {
  difficultyGridEl.innerHTML = "";
  const shouldShow = state.authenticated && (state.needsDifficultySelection || state.modeChooserOpen);
  difficultyModalEl.classList.toggle("is-hidden", !shouldShow);
  difficultyCloseButtonEl.classList.toggle("is-hidden", state.needsDifficultySelection);
  if (!shouldShow) {
    return;
  }

  const currentMode = state.user?.selectedClass || state.user?.difficulty || "";
  const currentModeLabel = state.user?.classLabel || state.user?.difficultyLabel || "Unset";
  const isChanging = Boolean(currentMode);
  difficultyEyebrowEl.textContent = isChanging ? "Switch class" : "Choose your class";
  difficultyTitleEl.textContent = isChanging ? "Change your class" : "Pick your class";
  difficultyCopyEl.textContent = isChanging
    ? `Your current class is ${currentModeLabel}. Switching to another class resets your Vault (TDA), play balance, run history, and leaderboard score.`
    : "Each class has different starting TDA, odds, deposit caps, and risk/reward profiles.";

  for (const option of state.difficultyOptions) {
    const card = document.createElement("button");
    card.type = "button";
    const isActive = currentMode === option.id;
    card.className = `difficulty-option ${isActive ? "is-active" : ""}`;
    
    const multiText = option.profitMultiplier > 1.0 ? `+${((option.profitMultiplier - 1.0) * 100).toFixed(0)}% profit` : "1:1 profit";
    const protectText = option.bankruptcyProtection ? "Protected" : "Game Over at R0";
    const capText = option.depositCap != null ? `Deposit cap ${currency(option.depositCap)}` : "No deposit cap";
    
    card.innerHTML = `
      <strong>${option.name}</strong>
      <span>Starting TDA: ${currency(option.startingTda)}</span>
      <small>${multiText} · ${protectText}</small>
      <small>${capText}</small>
      ${isActive ? '<small class="is-active-label">Current class</small>' : ''}
    `;
    card.addEventListener("click", async () => {
      if (isActive) {
        state.modeChooserOpen = false;
        renderDifficultyChooser();
        statusPillEl.textContent = `${option.name} class is already active.`;
        return;
      }

      if (
        currentMode &&
        !window.confirm(
          `Switch to ${option.name} class? This will reset your Vault (TDA), play balance, run history, and leaderboard score.`
        )
      ) {
        return;
      }

      try {
        const payload = await requestJson("/api/select-class", {
          method: "POST",
          body: JSON.stringify({ class: option.id }),
        });
        state.modeChooserOpen = false;
        applySnapshot(payload);
        // Reset session stats when changing mode
        resetSessionStats();
      } catch (error) {
        statusPillEl.textContent = error.message;
      }
    });
    difficultyGridEl.appendChild(card);
  }
}

function applySnapshot(data) {
  state.authenticated = data.authenticated;
  state.user = data.user;
  state.tda = data.tda || null;
  state.difficultyOptions = data.classOptions || data.difficultyOptions || [];
  state.needsDifficultySelection = data.needsDifficultySelection;
  if (!state.needsDifficultySelection) {
    state.modeChooserOpen = false;
  }
  renderResult(data);
  paintFinalGrid(data.lastSpin, data.winningLines);
  renderAccount();
  renderDifficultyChooser();
  updateControls();
  // Update easy cap warning
  updateEasyCapWarning();
}

async function refreshState() {
  const data = await requestJson("/api/state");
  applySnapshot(data);
  // Reset session stats on refresh
  resetSessionStats();
}

async function deposit() {
  const amount = Number.parseFloat(depositInput.value);
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
  if (state.isSpinning || !state.authenticated || state.needsDifficultySelection || state.autoSpin.enabled) {
    return;
  }
  statusPillEl.textContent = "Spinning reels...";
  try {
    const data = await requestJson("/api/spin", {
      method: "POST",
      body: JSON.stringify({ bet: state.bet }),
    });
    state.authenticated = data.authenticated;
    state.user = data.user;
    state.difficultyOptions = data.difficultyOptions || [];
    state.needsDifficultySelection = data.needsDifficultySelection;
    renderResult(data);
    renderAccount();
    renderDifficultyChooser();
    updateSessionStats(data);
    updateControls();
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
    // Reset session stats on login
    resetSessionStats();
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
    state.modeChooserOpen = false;
    stopAutoSpin();
    await refreshState();
    // Reset session stats on logout
    resetSessionStats();
  } catch (error) {
    statusPillEl.textContent = error.message;
  }
}

function openModeChooser() {
  if (!state.authenticated) {
    statusPillEl.textContent = "Sign in before choosing a mode.";
    return;
  }
  state.modeChooserOpen = true;
  renderDifficultyChooser();
}

// ================================
// EVENT LISTENERS
// ================================

document.querySelectorAll("[data-auth-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    state.authMode = button.dataset.authMode;
    renderAuthMode();
  });
});

document.querySelectorAll("[data-adjust]").forEach((button) => {
  button.addEventListener("click", () => {
    const delta = Number.parseInt(button.dataset.delta, 10);
    state.bet = Math.max(1, state.bet + delta);
    betTextInputEl.value = state.bet;
    updateControls();
  });
});

// Bet text input
betTextInputEl.addEventListener("input", (e) => {
  const value = parseInt(e.target.value, 10);
  if (!isNaN(value) && value > 0) {
    state.bet = value;
    updateControls();
  }
});

betTextInputEl.addEventListener("blur", (e) => {
  // Ensure valid value on blur
  const value = clamp(parseInt(e.target.value, 10) || 1, 1, parseInt(e.target.max, 10) || 1);
  state.bet = value;
  e.target.value = value;
  updateControls();
});

betTextInputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.target.blur();
    spinButton.focus();
  }
});

// Turbo toggle
turboToggleEl.addEventListener("click", toggleTurboMode);

// Auto-spin controls
document.querySelectorAll(".auto-spin-count").forEach((btn) => {
  btn.addEventListener("click", () => {
    selectAutoSpinCount(parseInt(btn.dataset.spins, 10));
  });
});

autoSpinStartEl.addEventListener("click", startAutoSpin);
autoSpinStopEl.addEventListener("click", stopAutoSpin);

// Theme change listener
window.addEventListener("themechange", (e) => {
  console.log("Theme changed to:", e.detail.theme);
});

authFormEl.addEventListener("submit", submitAuth);
logoutButtonEl.addEventListener("click", logout);
chooseModeButtonEl.addEventListener("click", openModeChooser);
depositButton.addEventListener("click", deposit);
spinButton.addEventListener("click", spin);
if (depositToPlayButton) depositToPlayButton.addEventListener("click", depositToPlay);
if (rechargeButton) rechargeButton.addEventListener("click", recharge);
difficultyCloseButtonEl.addEventListener("click", () => {
  state.modeChooserOpen = false;
  renderDifficultyChooser();
});
difficultyModalEl.addEventListener("click", (event) => {
  if (event.target !== difficultyModalEl || state.needsDifficultySelection) {
    return;
  }
  state.modeChooserOpen = false;
  renderDifficultyChooser();
});

// Initialize
createReels();
renderAuthMode();
refreshState().catch((error) => {
  statusPillEl.textContent = error.message;
});

// Set default auto-spin count
selectAutoSpinCount(10);
