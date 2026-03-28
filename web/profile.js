const profileStatusEl = document.getElementById("profile-status");
const formEl = document.getElementById("profile-form");
const displayNameInputEl = document.getElementById("display-name-input");
const bioInputEl = document.getElementById("bio-input");
const avatarUploadInputEl = document.getElementById("avatar-upload-input");
const bannerUploadInputEl = document.getElementById("banner-upload-input");
const clearAvatarButtonEl = document.getElementById("clear-avatar-button");
const clearBannerButtonEl = document.getElementById("clear-banner-button");

const bannerEl = document.getElementById("profile-banner");
const cardEl = document.getElementById("profile-card");
const avatarEl = document.getElementById("profile-avatar");
const avatarImageEl = document.getElementById("profile-avatar-image");
const avatarInitialsEl = document.getElementById("profile-avatar-initials");
const displayNameEl = document.getElementById("profile-display-name");
const usernameEl = document.getElementById("profile-username");
const bioEl = document.getElementById("profile-bio");
const modeMetaEl = document.getElementById("profile-mode-meta");
const rankGlobalEl = document.getElementById("rank-global");
const rankModeEl = document.getElementById("rank-mode");
const difficultyEl = document.getElementById("profile-difficulty");
const tdaEl = document.getElementById("profile-tda");
const playBalanceEl = document.getElementById("profile-play-balance");
const accountDaysEl = document.getElementById("account-days");
const hitRateEl = document.getElementById("profile-hit-rate");
const badgeGridEl = document.getElementById("badge-grid");
const skinOptionsEl = document.getElementById("skin-options");
const bannerOptionsEl = document.getElementById("banner-options");
const avatarOptionsEl = document.getElementById("avatar-options");
const achievementStatusEl = document.getElementById("achievement-status");
const achievementsUnlockedEl = document.getElementById("achievements-unlocked");
const achievementsTotalEl = document.getElementById("achievements-total");
const achievementsProgressEl = document.getElementById("achievements-progress");
const achievementGridEl = document.getElementById("achievement-grid");

const state = {
  profile: null,
  badges: [],
  storeBadges: [],
  cosmetics: null,
  inventory: {},
  stats: null,
  ranks: null,
  tda: null,
  achievements: [],
  achievementsTotal: 0,
  achievementsUnlocked: 0,
  achievementFilter: "all",
  avatarUpload: "",
  bannerUpload: "",
  clearAvatar: false,
  clearBanner: false,
};

function currency(value) {
  return `R${Number(value || 0).toFixed(2).replace(".00", "")}`;
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function rankLabel(value) {
  return value ? `#${value}` : "Unranked";
}

function requestJson(url, options = {}) {
  return fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    credentials: "same-origin",
    ...options,
  }).then(async (response) => {
    const contentType = response.headers.get("content-type") || "";
    const rawText = await response.text();
    const looksJson =
      contentType.includes("application/json") ||
      rawText.trim().startsWith("{") ||
      rawText.trim().startsWith("[");

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
  });
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Could not read the selected file."));
    reader.readAsDataURL(file);
  });
}

function updateThemeClasses(element, prefix, value) {
  [...element.classList]
    .filter((className) => className.startsWith(prefix))
    .forEach((className) => element.classList.remove(className));
  element.classList.add(`${prefix}${value}`);
}

function setFormDisabled(disabled) {
  formEl.querySelectorAll("input, textarea, button").forEach((element) => {
    element.disabled = disabled;
  });
}

function renderSignedOutState(message) {
  state.profile = null;
  state.badges = [];
  state.cosmetics = null;
  state.stats = null;
  state.ranks = null;

  displayNameEl.textContent = "Pixel Spinner";
  usernameEl.textContent = "@guest";
  bioEl.textContent = "Sign in from the main game page to unlock profile editing, badges, and leaderboard cosmetics.";
  modeMetaEl.textContent = "Class unset";
  rankGlobalEl.textContent = "Unranked";
  rankModeEl.textContent = "Unranked";
  difficultyEl.textContent = "Unset";
  if (tdaEl) tdaEl.textContent = "R0";
  if (playBalanceEl) playBalanceEl.textContent = "R0";
  accountDaysEl.textContent = "0";
  hitRateEl.textContent = "0.0%";
  avatarImageEl.src = "";
  avatarImageEl.classList.add("is-hidden");
  avatarInitialsEl.classList.remove("is-hidden");
  avatarInitialsEl.textContent = "PS";
  bannerEl.style.backgroundImage = "";
  bannerEl.classList.remove("profile-banner--uploaded");
  updateThemeClasses(cardEl, "skin-theme-", "skyline");
  updateThemeClasses(bannerEl, "banner-theme-", "aurora");
  updateThemeClasses(avatarEl, "avatar-theme-", "orbit");
  badgeGridEl.innerHTML = `<div class="badge-card badge-card--empty">Sign in and spin to earn profile badges.</div>`;
  skinOptionsEl.innerHTML = "";
  bannerOptionsEl.innerHTML = "";
  avatarOptionsEl.innerHTML = "";
  setFormDisabled(true);
  profileStatusEl.textContent = message;
}

function renderProfileCard() {
  if (!state.profile || !state.stats || !state.ranks) {
    return;
  }

  updateThemeClasses(cardEl, "skin-theme-", state.profile.selectedSkin);
  updateThemeClasses(bannerEl, "banner-theme-", state.profile.selectedBanner);
  updateThemeClasses(avatarEl, "avatar-theme-", state.profile.selectedAvatar);

  if (state.profile.bannerPath) {
    bannerEl.style.backgroundImage = `linear-gradient(rgba(20, 27, 45, 0.12), rgba(20, 27, 45, 0.22)), url('${state.profile.bannerPath}')`;
    bannerEl.classList.add("profile-banner--uploaded");
  } else {
    bannerEl.style.backgroundImage = "";
    bannerEl.classList.remove("profile-banner--uploaded");
  }

  if (state.profile.avatarPath) {
    avatarImageEl.src = state.profile.avatarPath;
    avatarImageEl.classList.remove("is-hidden");
    avatarInitialsEl.classList.add("is-hidden");
  } else {
    avatarImageEl.src = "";
    avatarImageEl.classList.add("is-hidden");
    avatarInitialsEl.classList.remove("is-hidden");
  }

  avatarInitialsEl.textContent = state.profile.initials;
  displayNameEl.textContent = state.profile.displayName;
  usernameEl.textContent = `@${state.profile.username}`;
  bioEl.textContent = state.profile.bio || "Add a short bio so other players know what kind of spinner you are.";
  modeMetaEl.textContent = `${state.stats.classLabel || state.stats.difficultyLabel} class • ${state.ranks.isTopTen ? "Top 10 unlocks active" : "Standard unlock track"}`;
  rankGlobalEl.textContent = rankLabel(state.ranks.globalRank);
  rankModeEl.textContent = rankLabel(state.ranks.classRank || state.ranks.modeRank);
  difficultyEl.textContent = state.stats.classLabel || state.stats.difficultyLabel;
  if (tdaEl) tdaEl.textContent = currency(state.tda?.total ?? 0);
  if (playBalanceEl) playBalanceEl.textContent = currency(state.tda?.playBalance ?? 0);
  accountDaysEl.textContent = String(state.stats.accountDays ?? 0);
  hitRateEl.textContent = percent(state.stats.hitRate);

  displayNameInputEl.value = state.profile.displayName;
  bioInputEl.value = state.profile.bio;
}

function renderBadges() {
  badgeGridEl.innerHTML = "";
  if (!state.badges.length) {
    badgeGridEl.innerHTML = `<div class="badge-card badge-card--empty">Spin a few rounds to start earning badges.</div>`;
    return;
  }

  for (const badge of state.badges) {
    const node = document.createElement("article");
    node.className = `badge badge--${badge.shape || 'hexagon'} badge--${badge.tone || 'bronze'}`;
    if (badge.animation) {
      node.classList.add(`badge--${badge.animation}`);
    }
    node.innerHTML = `
      <span class="badge__icon">${getBadgeIcon(badge.tone)}</span>
      <span class="badge__label">${badge.name}</span>
    `;
    node.title = badge.description;
    badgeGridEl.appendChild(node);
  }
  
  // Populate badge selector with store badges (purchasable ones)
  const badgeSelectorEl = document.getElementById("badge-selector");
  const selectedBadgeInput = document.getElementById("selected-badge-input");
  if (badgeSelectorEl && selectedBadgeInput) {
    selectedBadgeInput.innerHTML = '<option value="">None</option>';
    const ownedBadges = state.storeBadges.filter(b => b.owned);
    for (const badge of ownedBadges) {
      const option = document.createElement("option");
      option.value = badge.id;
      option.textContent = `${badge.icon || "🏅"} ${badge.name}`;
      if (state.profile.selectedBadge === badge.id) {
        option.selected = true;
      }
      selectedBadgeInput.appendChild(option);
    }
    badgeSelectorEl.style.display = ownedBadges.length > 0 ? "block" : "none";
  }
}

function renderOwnedThemes() {
  const themesGridEl = document.getElementById("owned-themes-grid");
  const currentThemeNameEl = document.getElementById("current-theme-name");
  
  if (!themesGridEl) return;
  
  themesGridEl.innerHTML = "";
  
  // Theme icons mapping
  const themeIcons = {
    synthwave: "🌆",
    synthwave90s: "🌃",
    gruvbox: "🐻",
    "tokyo-night": "🌃",
    "catppuccin-frappe": "🐱",
    "catppuccin-latte": "☕",
    "off-white": "⬜",
    oneui: "📱",
    "apple-glass": "🍎",
    apple: "🍎",
    dark: "🌙",
    light: "☀️",
  };
  
  const themeCategories = {
    synthwave: "Retro/Synth",
    synthwave90s: "Retro/Synth",
    gruvbox: "Developer",
    "tokyo-night": "Developer",
    "catppuccin-frappe": "Developer",
    "catppuccin-latte": "Developer",
    "off-white": "Clean/Modern",
    oneui: "Clean/Modern",
    "apple-glass": "Clean/Modern",
    apple: "Legacy",
    dark: "Legacy",
    light: "Legacy",
  };
  
  // Get owned themes from inventory
  const ownedThemes = state.inventory?.themes || [];
  
  // Always show default themes
  const defaultThemes = ["apple", "dark", "light"];
  const allThemes = [...new Set([...defaultThemes, ...ownedThemes])];
  
  // Current applied theme
  const currentTheme = state.profile.selectedTheme || window.themeEngine?.getCurrentTheme() || "apple";
  
  if (currentThemeNameEl) {
    const themeName = currentTheme.replace(/-/g, " ").replace(/\b\w/g, l => l.toUpperCase());
    currentThemeNameEl.textContent = themeName;
  }
  
  for (const themeId of allThemes) {
    const card = document.createElement("button");
    card.type = "button";
    const isOwned = ownedThemes.includes(themeId) || defaultThemes.includes(themeId);
    card.disabled = !isOwned;
    card.className = `theme-showcase-card ${currentTheme === themeId ? "is-active" : ""}`;
    card.dataset.theme = themeId;
    
    const icon = themeIcons[themeId] || "🎨";
    const category = themeCategories[themeId] || "Custom";
    const name = themeId.replace(/-/g, " ").replace(/\b\w/g, l => l.toUpperCase());
    
    card.innerHTML = `
      <div class="theme-showcase-card__preview" data-theme="${themeId}">${icon}</div>
      <div class="theme-showcase-card__name">${name}</div>
      <div class="theme-showcase-card__category">${category}</div>
      ${!isOwned ? '<small style="color: var(--muted);">🔒 Not owned</small>' : ''}
    `;
    
    if (isOwned) {
      card.addEventListener("click", async () => {
        if (!state.profile) return;
        
        // Apply theme using theme engine
        if (window.themeEngine) {
          window.themeEngine.applyTheme(themeId);
        }
        
        // Update state with new theme
        const oldTheme = state.profile.selectedTheme;
        state.profile.selectedTheme = themeId;
        
        // Update UI
        document.querySelectorAll(".theme-showcase-card").forEach(c => c.classList.remove("is-active"));
        card.classList.add("is-active");
        if (currentThemeNameEl) {
          currentThemeNameEl.textContent = name;
        }
        
        // Auto-save to backend if theme changed
        if (themeId !== oldTheme) {
          try {
            const payload = await requestJson("/api/profile", {
              method: "POST",
              body: JSON.stringify({
                displayName: state.profile.displayName,
                bio: state.profile.bio,
                selectedSkin: state.profile.selectedSkin,
                selectedBanner: state.profile.selectedBanner,
                selectedAvatar: state.profile.selectedAvatar,
                selectedBadge: state.profile.selectedBadge,
                selectedTheme: themeId,
              }),
            });
            applyPayload(payload);
            profileStatusEl.textContent = "Theme updated.";
          } catch (error) {
            // Revert on error
            state.profile.selectedTheme = oldTheme;
            profileStatusEl.textContent = error.message;
          }
        }
      });
    }
    
    themesGridEl.appendChild(card);
  }
}

function getBadgeIcon(tone) {
  const icons = {
    blue: "◆",
    gold: "★",
    green: "✦",
    rose: "♦",
    indigo: "◈",
    orange: "●",
    violet: "◇",
  };
  return icons[tone] || "◆";
}

function renderAchievements() {
  if (!state.achievements.length) {
    achievementGridEl.innerHTML = `<div class="badge-card badge-card--empty">Start playing to unlock achievements.</div>`;
    return;
  }

  const filtered = state.achievementFilter === "all" 
    ? state.achievements 
    : state.achievements.filter(a => a.category === state.achievementFilter);

  achievementGridEl.innerHTML = "";
  
  for (const achievement of filtered) {
    const card = document.createElement("article");
    card.className = `achievement-card ${achievement.unlocked ? "" : "achievement-card--locked"}`;
    
    card.innerHTML = `
      <div class="achievement-card__badge">
        <div class="badge badge--${achievement.shape || 'hexagon'} badge--${achievement.rarity || 'bronze'} ${achievement.animation ? `badge--${achievement.animation}` : ''}">
          <span>${achievement.unlocked ? getAchievementIcon(achievement.rarity) : "?"}</span>
        </div>
      </div>
      <div class="achievement-card__content">
        <strong>${achievement.unlocked ? achievement.name : "???"}</strong>
        <p>${achievement.unlocked ? achievement.description : "Keep playing to unlock this achievement."}</p>
        <div class="achievement-card__meta">
          <span class="achievement-card__category">${achievement.category}</span>
          <span class="achievement-card__rarity achievement-card__rarity--${achievement.rarity || 'bronze'}">${achievement.rarity || 'bronze'}</span>
        </div>
      </div>
    `;
    achievementGridEl.appendChild(card);
  }
}

function getAchievementIcon(rarity) {
  const icons = {
    bronze: "●",
    silver: "◐",
    gold: "★",
    platinum: "✦",
    diamond: "◆",
    radiant: "✴",
  };
  return icons[rarity] || "●";
}

function updateAchievementStats() {
  achievementsUnlockedEl.textContent = state.achievementsUnlocked;
  achievementsTotalEl.textContent = state.achievementsTotal;
  achievementsProgressEl.textContent = `${state.achievementsProgress}%`;
}

function renderOptions(container, items, selectedId, type) {
  container.innerHTML = "";
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.disabled = !item.unlocked;
    button.className = `cosmetic-card ${selectedId === item.id && item.unlocked ? "is-selected" : ""} ${item.unlocked ? "" : "is-locked"}`;
    button.dataset.value = item.id;
    button.dataset.type = type;
    button.innerHTML = `
      <span class="cosmetic-card__tag">${item.tag}</span>
      <strong>${item.name}</strong>
      <small>${item.requirementText}</small>
    `;
    button.addEventListener("click", () => {
      if (!state.profile || !item.unlocked) {
        return;
      }
      if (type === "skin") {
        state.profile.selectedSkin = item.id;
      } else if (type === "banner") {
        state.profile.selectedBanner = item.id;
      } else {
        state.profile.selectedAvatar = item.id;
      }
      renderProfileCard();
      renderCosmetics();
    });
    container.appendChild(button);
  }
}

function renderCosmetics() {
  if (!state.profile) {
    return;
  }
  renderOptions(skinOptionsEl, state.cosmetics?.skins || [], state.profile.selectedSkin, "skin");
  renderOptions(bannerOptionsEl, state.cosmetics?.banners || [], state.profile.selectedBanner, "banner");
  renderOptions(avatarOptionsEl, state.cosmetics?.avatars || [], state.profile.selectedAvatar, "avatar");
}

function applyPayload(payload) {
  state.profile = payload.profile;
  state.badges = payload.badges || [];
  state.storeBadges = payload.storeBadges || [];
  state.cosmetics = payload.cosmetics || { skins: [], banners: [], avatars: [] };
  state.stats = payload.stats;
  state.ranks = payload.ranks;
  state.tda = payload.tda || null;
  state.inventory = payload.stats?.inventory || {};
  setFormDisabled(false);
  renderProfileCard();
  renderBadges();
  renderOwnedThemes();
  renderCosmetics();
}

async function loadProfile() {
  try {
    const payload = await requestJson("/api/profile");
    applyPayload(payload);
    profileStatusEl.textContent = "Profile synced with live server progress.";
  } catch (error) {
    renderSignedOutState(error.message.includes("sign in") ? error.message : "Sign in to view and edit your profile.");
  }
}

async function loadAchievements() {
  try {
    const data = await requestJson("/api/achievements");
    state.achievements = data.achievements;
    state.achievementsTotal = data.total;
    state.achievementsUnlocked = data.unlocked;
    state.achievementsProgress = data.progress;
    updateAchievementStats();
    renderAchievements();
    achievementStatusEl.textContent = `${data.unlocked}/${data.total} achievements unlocked.`;
  } catch (error) {
    achievementStatusEl.textContent = error.message.includes("sign in") ? "Sign in to view achievements." : error.message;
    state.achievements = [];
  }
}

// Achievement filter handling
document.querySelectorAll(".achievement-filter").forEach(button => {
  button.addEventListener("click", () => {
    state.achievementFilter = button.dataset.filter;
    document.querySelectorAll(".achievement-filter").forEach(b => {
      b.classList.toggle("is-active", b === button);
    });
    renderAchievements();
  });
});

async function submitProfile(event) {
  event.preventDefault();
  if (!state.profile) {
    profileStatusEl.textContent = "Sign in to save profile changes.";
    return;
  }
  try {
    const payload = await requestJson("/api/profile", {
      method: "POST",
      body: JSON.stringify({
        displayName: displayNameInputEl.value.trim(),
        bio: bioInputEl.value.trim(),
        selectedSkin: state.profile.selectedSkin,
        selectedBanner: state.profile.selectedBanner,
        selectedAvatar: state.profile.selectedAvatar,
        selectedBadge: state.profile.selectedBadge,
        selectedTheme: state.profile.selectedTheme,
        avatarUpload: state.avatarUpload,
        bannerUpload: state.bannerUpload,
        clearAvatar: state.clearAvatar,
        clearBanner: state.clearBanner,
      }),
    });
    applyPayload(payload);
    state.avatarUpload = "";
    state.bannerUpload = "";
    state.clearAvatar = false;
    state.clearBanner = false;
    avatarUploadInputEl.value = "";
    bannerUploadInputEl.value = "";
    profileStatusEl.textContent = "Profile updated.";
  } catch (error) {
    profileStatusEl.textContent = error.message;
  }
}

avatarUploadInputEl.addEventListener("change", async () => {
  const [file] = avatarUploadInputEl.files;
  if (!file || !state.profile) {
    return;
  }
  try {
    state.avatarUpload = await readFileAsDataUrl(file);
    state.clearAvatar = false;
    profileStatusEl.textContent = "Avatar selected. Save profile to upload it.";
  } catch (error) {
    profileStatusEl.textContent = error.message;
  }
});

bannerUploadInputEl.addEventListener("change", async () => {
  const [file] = bannerUploadInputEl.files;
  if (!file || !state.profile) {
    return;
  }
  try {
    state.bannerUpload = await readFileAsDataUrl(file);
    state.clearBanner = false;
    profileStatusEl.textContent = "Banner selected. Save profile to upload it.";
  } catch (error) {
    profileStatusEl.textContent = error.message;
  }
});

clearAvatarButtonEl.addEventListener("click", () => {
  if (!state.profile) {
    return;
  }
  state.clearAvatar = true;
  state.avatarUpload = "";
  avatarUploadInputEl.value = "";
  profileStatusEl.textContent = "Uploaded avatar will be removed when you save.";
});

clearBannerButtonEl.addEventListener("click", () => {
  if (!state.profile) {
    return;
  }
  state.clearBanner = true;
  state.bannerUpload = "";
  bannerUploadInputEl.value = "";
  profileStatusEl.textContent = "Uploaded banner will be removed when you save.";
});

formEl.addEventListener("submit", submitProfile);

// Badge selector - auto-save when selection changes
const selectedBadgeInputEl = document.getElementById("selected-badge-input");
if (selectedBadgeInputEl) {
  selectedBadgeInputEl.addEventListener("change", async () => {
    if (!state.profile) return;
    const newBadge = selectedBadgeInputEl.value;
    state.profile.selectedBadge = newBadge;
    try {
      const payload = await requestJson("/api/profile", {
        method: "POST",
        body: JSON.stringify({
          displayName: state.profile.displayName,
          bio: state.profile.bio,
          selectedSkin: state.profile.selectedSkin,
          selectedBanner: state.profile.selectedBanner,
          selectedAvatar: state.profile.selectedAvatar,
          selectedBadge: newBadge,
          selectedTheme: state.profile.selectedTheme,
        }),
      });
      applyPayload(payload);
      profileStatusEl.textContent = "Badge updated.";
    } catch (error) {
      profileStatusEl.textContent = error.message;
    }
  });
}

renderSignedOutState("Loading profile...");
loadProfile();
loadAchievements();
