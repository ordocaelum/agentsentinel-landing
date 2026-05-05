// AgentSentinel Onboarding Wizard
// 3-step wizard state machine with code generation per language/framework.

import { fetchDashboardConfig, postTestEvent } from "./customer-api.js";

// ── State ────────────────────────────────────────────────────────────────────

const state = {
  step: 1,
  lang: "python",   // "python" | "typescript"
  licenseKey: null,
  webhookUrl: null,
  dashboardUrl: null,
  testPassed: false,
};

// ── Initialise ───────────────────────────────────────────────────────────────

export async function initOnboarding() {
  const params = new URLSearchParams(window.location.search);
  state.licenseKey = params.get("token");

  if (!state.licenseKey) {
    showError("No license token found in URL. Please use the link from your purchase email.");
    return;
  }

  try {
    const config = await fetchDashboardConfig(state.licenseKey);
    state.webhookUrl = config.webhook_url;
    state.dashboardUrl = config.live_url;

    // Prefill hidden elements
    setTextContent("#onb-license-key", state.licenseKey);
    setTextContent("#onb-webhook-url", state.webhookUrl);
  } catch (e) {
    showError("Could not load your dashboard configuration. Please check your link or contact support.");
    return;
  }

  renderStep(1);
  bindEvents();
}

// ── Render ───────────────────────────────────────────────────────────────────

function renderStep(n) {
  state.step = n;
  document.querySelectorAll(".onb-step").forEach((el) => {
    el.classList.toggle("hidden", parseInt(el.dataset.step) !== n);
  });
  document.querySelectorAll(".onb-step-indicator").forEach((el) => {
    const s = parseInt(el.dataset.step);
    el.classList.toggle("active", s === n);
    el.classList.toggle("done", s < n);
  });
  if (n === 2) renderCode();
}

// ── Code generation ──────────────────────────────────────────────────────────

function renderCode() {
  const { lang, licenseKey, webhookUrl } = state;
  const installBlock = document.getElementById("onb-install-code");
  const configBlock  = document.getElementById("onb-config-code");
  const testBlock    = document.getElementById("onb-test-code");

  if (lang === "python") {
    if (installBlock) installBlock.textContent = `pip install agentsentinel-core`;

    if (configBlock) configBlock.textContent = `from agentsentinel import AgentGuard, AgentPolicy

policy = AgentPolicy(
    daily_budget=10.0,
    webhook_url="${webhookUrl}",
    webhook_key="${licenseKey}",
    stream_events=True,
)
guard = AgentGuard(policy=policy, license_key="${licenseKey}")

@guard.protect(tool_name="my_tool", cost=0.01)
def my_tool(query: str) -> str:
    return f"Result for: {query}"`;

    if (testBlock) testBlock.textContent = `# Run this to send a test event to your dashboard
import agentsentinel as _as
_as.guard.AgentGuard(
    policy=_as.policy.AgentPolicy(
        webhook_url="${webhookUrl}",
        webhook_key="${licenseKey}",
    ),
    license_key="${licenseKey}",
)._stream_tool_event("test_connection", "allowed", 0.0, {"source": "test_script"})
print("✅ Test event sent! Check your dashboard.")`;
  } else {
    // TypeScript
    if (installBlock) installBlock.textContent = `npm install @agentsentinel/sdk`;

    if (configBlock) configBlock.textContent = `import { AgentGuard, AgentPolicy } from "@agentsentinel/sdk";

const policy = new AgentPolicy({
  dailyBudget: 10.0,
  webhookUrl: "${webhookUrl}",
  webhookKey: "${licenseKey}",
  streamEvents: true,
});
const guard = new AgentGuard({ policy });

const myTool = guard.protect(
  async (query: string) => \`Result for: \${query}\`,
  { toolName: "my_tool", cost: 0.01 }
);`;

    if (testBlock) testBlock.textContent = `// Run this to send a test event to your dashboard
import { AgentGuard, AgentPolicy } from "@agentsentinel/sdk";
const guard = new AgentGuard({
  policy: new AgentPolicy({
    webhookUrl: "${webhookUrl}",
    webhookKey: "${licenseKey}",
  }),
});
// Trigger a flush — events will appear on your dashboard within ~5 seconds
guard.destroy();
console.log("✅ Test event sent! Check your dashboard.");`;
  }
}

// ── Event bindings ───────────────────────────────────────────────────────────

function bindEvents() {
  // Language picker
  document.querySelectorAll("[data-lang]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.lang = btn.dataset.lang;
      document.querySelectorAll("[data-lang]").forEach((b) => {
        b.classList.toggle("lang-active", b.dataset.lang === state.lang);
      });
      if (state.step === 2) renderCode();
    });
  });

  // Step navigation
  const btnNext1 = document.getElementById("onb-next-1");
  if (btnNext1) btnNext1.addEventListener("click", () => renderStep(2));

  const btnNext2 = document.getElementById("onb-next-2");
  if (btnNext2) btnNext2.addEventListener("click", () => renderStep(3));

  const btnPrev2 = document.getElementById("onb-prev-2");
  if (btnPrev2) btnPrev2.addEventListener("click", () => renderStep(1));

  const btnPrev3 = document.getElementById("onb-prev-3");
  if (btnPrev3) btnPrev3.addEventListener("click", () => renderStep(2));

  // Test connection button
  const btnTest = document.getElementById("onb-test-btn");
  if (btnTest) {
    btnTest.addEventListener("click", async () => {
      btnTest.disabled = true;
      btnTest.textContent = "Sending…";
      try {
        await postTestEvent(state.licenseKey);
        state.testPassed = true;
        showTestSuccess();
      } catch {
        showTestError();
      } finally {
        btnTest.disabled = false;
        btnTest.textContent = "Send Test Event";
      }
    });
  }

  // Start monitoring button
  const btnStart = document.getElementById("onb-start-btn");
  if (btnStart) {
    btnStart.addEventListener("click", () => {
      window.location.href = state.dashboardUrl ||
        `/dashboard/main.html?token=${encodeURIComponent(state.licenseKey)}`;
    });
  }

  // Copy buttons (all elements with data-copy-target)
  document.querySelectorAll("[data-copy-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.getElementById(btn.dataset.copyTarget);
      if (!target) return;
      navigator.clipboard.writeText(target.textContent.trim()).then(() => {
        const orig = btn.textContent;
        btn.textContent = "Copied!";
        btn.classList.add("copied");
        setTimeout(() => { btn.textContent = orig; btn.classList.remove("copied"); }, 2000);
      });
    });
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setTextContent(selector, text) {
  const el = document.querySelector(selector);
  if (el) el.textContent = text;
}

function showError(msg) {
  const el = document.getElementById("onb-error");
  if (el) { el.textContent = msg; el.classList.remove("hidden"); }
}

function showTestSuccess() {
  const el = document.getElementById("onb-test-result");
  if (el) {
    el.innerHTML = `✅ <strong>Test event received!</strong> Events will appear on your dashboard within ~5 seconds.`;
    el.className = "text-green-400 mt-3 text-sm";
    el.classList.remove("hidden");
  }
  const btnStart = document.getElementById("onb-start-btn");
  if (btnStart) btnStart.classList.remove("opacity-50", "cursor-not-allowed");
}

function showTestError() {
  const el = document.getElementById("onb-test-result");
  if (el) {
    el.innerHTML = `❌ Could not send test event. Check your license key and try again.`;
    el.className = "text-red-400 mt-3 text-sm";
    el.classList.remove("hidden");
  }
}
