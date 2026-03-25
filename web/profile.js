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
const rankTopSpinEl = document.getElementById("rank-top-spin");
const rankFrequencyEl = document.getElementById("rank-frequency");
const accountDaysEl = document.getElementById("account-days");
const hitRateEl = document.getElementById("profile-hit-rate");
const badgeGridEl = document.getElementById("badge-grid");
const skinOptionsEl = document.getElementById("skin-options");
const bannerOptionsEl = document.getElementById("banner-options");
const avatarOptionsEl = document.getElementById("avatar-options");

const state = {
  profile: null,
  badges: [],
  cosmetics: null,
  stats: null,
  ranks: null,
  avatarUpload: "",
  bannerUpload: "",
  clearAvatar: false,
  clearBanner: false,
};

function percent(value) {
  return `${(Number(value) * 100).toFixed(1)}%`;
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
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Something went wrong.");
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

function renderProfileCard() {
  if (!state.profile) {
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
  rankTopSpinEl.textContent = state.ranks?.globalTopSpinRank ? `#${state.ranks.globalTopSpinRank}` : "Unranked";
  rankFrequencyEl.textContent = state.ranks?.frequentWinnerRank ? `#${state.ranks.frequentWinnerRank}` : "Unranked";
  accountDaysEl.textContent = state.stats?.accountDays ?? 0;
  hitRateEl.textContent = percent(state.stats?.hitRate ?? 0);

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
    node.className = `badge-card badge-card--${badge.tone}`;
    node.innerHTML = `
      <strong>${badge.name}</strong>
      <p>${badge.description}</p>
    `;
    badgeGridEl.appendChild(node);
  }
}

function renderOptions(container, items, selectedId, type) {
  container.innerHTML = "";
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `cosmetic-card ${selectedId === item.id ? "is-selected" : ""}`;
    button.dataset.value = item.id;
    button.dataset.type = type;
    button.innerHTML = `
      <span class="cosmetic-card__tag">${item.elite ? "Top 10" : "Unlocked"}</span>
      <strong>${item.name}</strong>
      <small>${item.id.replace(/_/g, " ")}</small>
    `;
    button.addEventListener("click", () => {
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
  renderOptions(skinOptionsEl, state.cosmetics?.skins || [], state.profile.selectedSkin, "skin");
  renderOptions(bannerOptionsEl, state.cosmetics?.banners || [], state.profile.selectedBanner, "banner");
  renderOptions(avatarOptionsEl, state.cosmetics?.avatars || [], state.profile.selectedAvatar, "avatar");
}

function applyPayload(payload) {
  state.profile = payload.profile;
  state.badges = payload.badges;
  state.cosmetics = payload.cosmetics;
  state.stats = payload.stats;
  state.ranks = payload.ranks;
  renderProfileCard();
  renderBadges();
  renderCosmetics();
}

async function loadProfile() {
  try {
    const payload = await requestJson("/api/profile");
    applyPayload(payload);
    profileStatusEl.textContent = "Profile synced with live server badges.";
  } catch (error) {
    profileStatusEl.textContent = error.message;
  }
}

async function submitProfile(event) {
  event.preventDefault();
  try {
    const payload = await requestJson("/api/profile", {
      method: "POST",
      body: JSON.stringify({
        displayName: displayNameInputEl.value.trim(),
        bio: bioInputEl.value.trim(),
        selectedSkin: state.profile.selectedSkin,
        selectedBanner: state.profile.selectedBanner,
        selectedAvatar: state.profile.selectedAvatar,
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
  if (!file) {
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
  if (!file) {
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
  state.clearAvatar = true;
  state.avatarUpload = "";
  avatarUploadInputEl.value = "";
  profileStatusEl.textContent = "Uploaded avatar will be removed when you save.";
});

clearBannerButtonEl.addEventListener("click", () => {
  state.clearBanner = true;
  state.bannerUpload = "";
  bannerUploadInputEl.value = "";
  profileStatusEl.textContent = "Uploaded banner will be removed when you save.";
});

formEl.addEventListener("submit", submitProfile);

loadProfile();
