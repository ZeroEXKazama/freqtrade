import { MetaMaskSDK } from "https://esm.sh/@metamask/sdk@0.33.1";

const sdk = new MetaMaskSDK({
  dappMetadata: {
    name: "Bot Management Dashboard",
    url: window.location.origin,
  },
  checkInstallationImmediately: false,
});

const ethereum = sdk.getProvider();

let authToken = localStorage.getItem("dashboard_access_token") || "";
let currentWallet = localStorage.getItem("dashboard_wallet") || "";
let activeStrategyId = Number(localStorage.getItem("dashboard_strategy_id") || 0);

function shortWallet(address) {
  if (!address) {
    return "disconnected";
  }
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

function setWalletState() {
  document.getElementById("wallet-pill").textContent = `Wallet: ${shortWallet(currentWallet)}`;
  document.getElementById("auth-wallet").textContent = currentWallet || "";
}

function toNumber(value, fallback) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function setStatus(id, message, isError = false) {
  const el = document.getElementById(id);
  el.textContent = message;
  el.classList.toggle("error", isError);
}

async function apiRequest(path, { method = "GET", body, auth = true } = {}) {
  const headers = {
    "Content-Type": "application/json",
  };
  if (auth && authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }
  const response = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const payload = await response.json();
      detail = payload.detail || JSON.stringify(payload);
    } catch (_error) {
      detail = `HTTP ${response.status}`;
    }
    throw new Error(detail);
  }
  return response.json();
}

function saveAuth(token, wallet) {
  authToken = token;
  currentWallet = wallet;
  localStorage.setItem("dashboard_access_token", authToken);
  localStorage.setItem("dashboard_wallet", currentWallet);
  setWalletState();
}

function clearAuth() {
  authToken = "";
  currentWallet = "";
  activeStrategyId = 0;
  localStorage.removeItem("dashboard_access_token");
  localStorage.removeItem("dashboard_wallet");
  localStorage.removeItem("dashboard_strategy_id");
  setWalletState();
}

function getStrategyParametersFromBuilder() {
  const stoplossPct = toNumber(document.getElementById("strategy-stoploss-pct").value, 8);
  const takeProfitPct = toNumber(document.getElementById("strategy-take-profit-pct").value, 15);

  return {
    template: document.getElementById("strategy-template").value,
    timeframe: document.getElementById("strategy-timeframe").value,
    stake_amount: toNumber(document.getElementById("strategy-stake-amount").value, 100),
    max_open_trades: Math.max(1, Math.round(toNumber(document.getElementById("strategy-max-open-trades").value, 3))),
    stoploss: -Math.abs(stoplossPct) / 100,
    take_profit: Math.abs(takeProfitPct) / 100,
    trailing_stop: document.getElementById("strategy-trailing-stop").value === "true",
    leverage: {
      mode: document.getElementById("strategy-leverage-mode").value,
      value: Math.max(1, Math.round(toNumber(document.getElementById("strategy-leverage-value").value, 1))),
    },
    signals: {
      entry: document.getElementById("strategy-entry-signal").value,
      confirmation_candles: Math.max(
        1,
        Math.round(toNumber(document.getElementById("strategy-confirmation-candles").value, 2))
      ),
    },
    risk: {
      level: document.getElementById("strategy-risk-level").value,
      max_daily_loss_pct: Math.abs(toNumber(document.getElementById("strategy-max-daily-loss").value, 5)),
    },
  };
}

function renderStrategyPreview() {
  const preview = document.getElementById("strategy-json-preview");
  preview.textContent = JSON.stringify(getStrategyParametersFromBuilder(), null, 2);
}

function setChecklistState(id, isComplete) {
  const dot = document.getElementById(id);
  dot.classList.toggle("ok", Boolean(isComplete));
}

function renderConfigLists(strategies, exchanges) {
  const strategyListEl = document.getElementById("strategy-list");
  const exchangeListEl = document.getElementById("exchange-list");

  strategyListEl.innerHTML = "";
  exchangeListEl.innerHTML = "";

  if (strategies.length === 0) {
    strategyListEl.innerHTML = "<li>No strategies saved yet.</li>";
  } else {
    strategies.forEach((strategy) => {
      const li = document.createElement("li");
      li.textContent = `${strategy.name} (id: ${strategy.id})`;
      strategyListEl.appendChild(li);
    });
  }

  if (exchanges.length === 0) {
    exchangeListEl.innerHTML = "<li>No exchange credentials saved yet.</li>";
  } else {
    exchanges.forEach((exchange) => {
      const li = document.createElement("li");
      li.textContent = `${exchange.exchange_name}: ${exchange.api_key_masked}`;
      exchangeListEl.appendChild(li);
    });
  }
}

async function connectAndSignIn() {
  setStatus("auth-status", "Connecting wallet...");
  if (!ethereum) {
    setStatus("auth-status", "MetaMask provider not detected.", true);
    return;
  }
  try {
    const accounts = await ethereum.request({ method: "eth_requestAccounts" });
    if (!accounts || accounts.length === 0) {
      throw new Error("No wallet account returned.");
    }
    const walletAddress = accounts[0];
    const challenge = await apiRequest("/api/auth/challenge", {
      method: "POST",
      body: { wallet_address: walletAddress },
      auth: false,
    });
    const signature = await ethereum.request({
      method: "personal_sign",
      params: [challenge.message, walletAddress],
    });
    const auth = await apiRequest("/api/auth/verify", {
      method: "POST",
      body: {
        wallet_address: walletAddress,
        nonce: challenge.nonce,
        message: challenge.message,
        signature,
      },
      auth: false,
    });
    saveAuth(auth.access_token, walletAddress.toLowerCase());
    setStatus("auth-status", "Signed in successfully.");
    await refreshDashboardAndConfig();
  } catch (error) {
    setStatus("auth-status", error.message, true);
  }
}

async function devLogin() {
  setStatus("auth-status", "Creating development session...");
  try {
    const demoWallet = "0x1111111111111111111111111111111111111111";
    const auth = await apiRequest("/api/auth/dev-login", {
      method: "POST",
      body: { wallet_address: demoWallet },
      auth: false,
    });
    saveAuth(auth.access_token, demoWallet);
    setStatus("auth-status", "Development session ready.");
    await refreshDashboardAndConfig();
  } catch (error) {
    setStatus("auth-status", error.message, true);
  }
}

async function saveExchangeCredentials() {
  try {
    const payload = {
      exchange_name: document.getElementById("exchange-name").value,
      api_key: document.getElementById("exchange-api-key").value,
      api_secret: document.getElementById("exchange-api-secret").value,
      passphrase: document.getElementById("exchange-passphrase").value || null,
    };
    const response = await apiRequest("/api/exchange-credentials", {
      method: "PUT",
      body: payload,
    });
    setStatus(
      "exchange-status",
      `Saved ${response.exchange_name} credentials (${response.api_key_masked}).`
    );
    document.getElementById("exchange-api-key").value = "";
    document.getElementById("exchange-api-secret").value = "";
    document.getElementById("exchange-passphrase").value = "";
    await refreshDashboardAndConfig();
  } catch (error) {
    setStatus("exchange-status", error.message, true);
  }
}

async function saveStrategy() {
  try {
    const parameters = getStrategyParametersFromBuilder();
    const payload = {
      name: document.getElementById("strategy-name").value,
      parameters,
      enabled: true,
    };
    const strategy = await apiRequest("/api/strategies", {
      method: "POST",
      body: payload,
    });
    activeStrategyId = strategy.id;
    localStorage.setItem("dashboard_strategy_id", String(activeStrategyId));
    document.getElementById("active-strategy").textContent = `Active strategy id: ${strategy.id}`;
    setStatus("strategy-status", `Strategy ${strategy.name} saved.`);
    await refreshDashboardAndConfig();
  } catch (error) {
    setStatus("strategy-status", error.message, true);
  }
}

async function saveTelegramConfig() {
  try {
    const payload = {
      bot_token: document.getElementById("telegram-token").value,
      chat_id: document.getElementById("telegram-chat-id").value,
    };
    const response = await apiRequest("/api/telegram", {
      method: "PUT",
      body: payload,
    });
    setStatus("bot-status", `Telegram saved (${response.chat_id_masked}).`);
    document.getElementById("telegram-token").value = "";
    await refreshDashboardAndConfig();
  } catch (error) {
    setStatus("bot-status", error.message, true);
  }
}

async function runBot() {
  try {
    let strategyId = activeStrategyId;
    if (!strategyId) {
      const strategies = await apiRequest("/api/strategies");
      if (!strategies.length) {
        throw new Error("Save a strategy before starting the bot.");
      }
      strategyId = strategies[0].id;
      activeStrategyId = strategyId;
      localStorage.setItem("dashboard_strategy_id", String(activeStrategyId));
    }
    const response = await apiRequest("/api/bot/run", {
      method: "POST",
      body: { strategy_id: strategyId },
    });
    setStatus("bot-status", `Bot is ${response.status}.`);
    await refreshDashboardAndConfig();
  } catch (error) {
    setStatus("bot-status", error.message, true);
  }
}

async function stopBot() {
  try {
    const response = await apiRequest("/api/bot/stop", { method: "POST" });
    setStatus("bot-status", `Bot is ${response.status}.`);
    await refreshDashboardAndConfig();
  } catch (error) {
    setStatus("bot-status", error.message, true);
  }
}

function renderOverview(overview, strategies, exchanges) {
  document.getElementById("stat-bot-status").textContent = overview.bot_status;
  document.getElementById("stat-strategy-count").textContent = String(overview.strategy_count);
  document.getElementById("stat-exchange-count").textContent = String(overview.exchange_connections);
  document.getElementById("stat-telegram").textContent = overview.telegram_configured ? "yes" : "no";
  document.getElementById("stat-total-trades").textContent = String(overview.metrics.total_trades);
  document.getElementById("stat-open-positions").textContent = String(overview.metrics.open_positions);
  document.getElementById("stat-win-rate").textContent = `${overview.metrics.win_rate}%`;
  document.getElementById("stat-drawdown").textContent = `${overview.metrics.max_drawdown}%`;

  setChecklistState("check-auth", Boolean(authToken));
  setChecklistState("check-exchange", overview.exchange_connections > 0);
  setChecklistState("check-strategy", overview.strategy_count > 0);
  setChecklistState("check-telegram", overview.telegram_configured);
  setChecklistState("check-running", overview.bot_status === "running");
  renderConfigLists(strategies, exchanges);
}

async function refreshDashboardAndConfig() {
  if (!authToken) {
    setStatus("dashboard-status", "Sign in to load dashboard.");
    setChecklistState("check-auth", false);
    setChecklistState("check-exchange", false);
    setChecklistState("check-strategy", false);
    setChecklistState("check-telegram", false);
    setChecklistState("check-running", false);
    renderConfigLists([], []);
    return;
  }
  try {
    const [overview, strategies, exchanges] = await Promise.all([
      apiRequest("/api/dashboard/overview"),
      apiRequest("/api/strategies"),
      apiRequest("/api/exchange-credentials"),
    ]);
    renderOverview(overview, strategies, exchanges);
    setStatus("dashboard-status", "Dashboard updated.");
  } catch (error) {
    setStatus("dashboard-status", error.message, true);
  }
}

async function boot() {
  renderStrategyPreview();
  [
    "strategy-template",
    "strategy-timeframe",
    "strategy-stake-amount",
    "strategy-max-open-trades",
    "strategy-stoploss-pct",
    "strategy-take-profit-pct",
    "strategy-trailing-stop",
    "strategy-leverage-mode",
    "strategy-leverage-value",
    "strategy-entry-signal",
    "strategy-risk-level",
    "strategy-max-daily-loss",
    "strategy-confirmation-candles",
  ].forEach((inputId) => {
    document.getElementById(inputId).addEventListener("input", renderStrategyPreview);
    document.getElementById(inputId).addEventListener("change", renderStrategyPreview);
  });

  setWalletState();
  document.getElementById("btn-connect-wallet").addEventListener("click", connectAndSignIn);
  document.getElementById("btn-dev-login").addEventListener("click", devLogin);
  document.getElementById("btn-logout").addEventListener("click", () => {
    clearAuth();
    setStatus("auth-status", "Logged out.");
    setStatus("dashboard-status", "Sign in to load dashboard.");
    renderConfigLists([], []);
  });
  document.getElementById("btn-save-exchange").addEventListener("click", saveExchangeCredentials);
  document.getElementById("btn-save-strategy").addEventListener("click", saveStrategy);
  document.getElementById("btn-save-telegram").addEventListener("click", saveTelegramConfig);
  document.getElementById("btn-run-bot").addEventListener("click", runBot);
  document.getElementById("btn-stop-bot").addEventListener("click", stopBot);
  document.getElementById("btn-refresh-dashboard").addEventListener("click", refreshDashboardAndConfig);

  if (authToken) {
    try {
      const profile = await apiRequest("/api/me");
      currentWallet = profile.wallet_address;
      setWalletState();
      await refreshDashboardAndConfig();
      setStatus("auth-status", "Restored existing session.");
    } catch (_error) {
      clearAuth();
      setStatus("auth-status", "Previous session expired, please sign in again.");
      renderConfigLists([], []);
    }
  } else {
    renderConfigLists([], []);
  }
}

boot();

