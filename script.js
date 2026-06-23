let agents = [];
let groupedAgents = [];
const executionState = {
  isRunning: false
};

const nav = document.querySelector("[data-nav]");
const menu = document.querySelector("[data-menu]");
const menuButton = document.querySelector("[data-menu-button]");
const agentList = document.querySelector("[data-agent-list]");
const agentName = document.querySelector("[data-agent-name]");
const agentDescription = document.querySelector("[data-agent-description]");
const agentPrompt = document.querySelector("[data-agent-prompt]");
const agentOutput = document.querySelector("[data-agent-output]");
const agentStatus = document.querySelector("[data-agent-status]");
const workflowRunningNotice = document.querySelector("[data-workflow-running]");
const copyJsonButton = document.querySelector("[data-copy-json]");
const downloadExcelLink = document.querySelector("[data-download-excel]");
const agentProviderInput = document.querySelector("[data-agent-provider]");
const agentCloudModelInput = document.querySelector("[data-agent-cloud-model]");
const prdControls = document.querySelector("[data-prd-controls]");
const runAgentButton = document.querySelector("[data-run-agent]");
const prdTextInput = document.querySelector("[data-prd-text]");
const prdFileInput = document.querySelector("[data-prd-file]");
let selectedAgent = agents[0];
let runtimeCloudModels = [];
let runtimeProviderOptions = {};
let latestJsonOutput = "";

const API_BASE = "http://localhost:8080";

const getAgentCapabilities = (agent) => {
  if (!agent || typeof agent !== "object") {
    return {};
  }
  const capabilities = agent.capabilities && typeof agent.capabilities === "object" ? agent.capabilities : {};
  // Backward compatibility: tolerate flat `supportsExcelExport` shape if present.
  if (typeof agent.supportsExcelExport === "boolean" && capabilities.supportsExcelExport === undefined) {
    return {
      ...capabilities,
      supportsExcelExport: agent.supportsExcelExport
    };
  }
  return capabilities;
};
const supportsExcelExport = (agent) => {
  if (!agent || agent.id !== "prd_pipeline") {
    return false;
  }
  const rawValue = getAgentCapabilities(agent).supportsExcelExport;
  if (typeof rawValue === "boolean") {
    return rawValue;
  }
  if (typeof rawValue === "string") {
    return rawValue.trim().toLowerCase() === "true";
  }
  return false;
};
const isPrdPipelineAgent = () => selectedAgent?.id === "prd_pipeline";

const clearAgentOutputState = () => {
  latestJsonOutput = "";
  agentOutput.textContent = "Start the agent server, then run an agent here.";
  agentStatus.textContent = "Cloud mode / Gemini";
  hideExcelDownload();
};

// Each agent switch starts from a clean slate to avoid stale workflow context.
const resetInputsForAgentSwitch = () => {
  if (agentPrompt) {
    agentPrompt.value = "";
  }
  if (prdTextInput) {
    prdTextInput.value = "";
  }
  if (prdFileInput) {
    prdFileInput.value = "";
  }
  clearAgentOutputState();
};

const updateExecutionLockUi = () => {
  const isRunning = executionState.isRunning;
  if (runAgentButton) {
    runAgentButton.disabled = isRunning;
  }
  if (agentPrompt) {
    agentPrompt.disabled = isRunning;
  }
  if (prdTextInput) {
    prdTextInput.disabled = isRunning;
  }
  if (prdFileInput) {
    prdFileInput.disabled = isRunning;
  }
  if (agentProviderInput) {
    agentProviderInput.disabled = isRunning;
  }
  if (agentCloudModelInput) {
    agentCloudModelInput.disabled = isRunning || agentProviderInput?.value !== "cloud";
  }
  if (workflowRunningNotice) {
    workflowRunningNotice.hidden = !isRunning;
  }
};

const hideExcelDownload = () => {
  if (!downloadExcelLink) {
    return;
  }
  downloadExcelLink.hidden = true;
  downloadExcelLink.classList.remove("is-disabled");
  downloadExcelLink.removeAttribute("href");
  downloadExcelLink.removeAttribute("download");
};

const showExcelDownloadPending = () => {
  if (!downloadExcelLink) {
    return;
  }
  downloadExcelLink.hidden = false;
  downloadExcelLink.classList.add("is-disabled");
  downloadExcelLink.removeAttribute("href");
  downloadExcelLink.removeAttribute("download");
};

const updateExcelDownloadLink = (payload) => {
  if (!downloadExcelLink) {
    return;
  }
  if (!isPrdPipelineAgent()) {
    hideExcelDownload();
    return;
  }
  const excel = payload?.artifacts?.excel;
  if (!supportsExcelExport(selectedAgent) || !excel?.download_url) {
    hideExcelDownload();
    return;
  }
  const filename = typeof excel.filename === "string" && excel.filename.trim() ? excel.filename : "PRD_PRD_Analysis.xlsx";
  downloadExcelLink.href = `${API_BASE}${excel.download_url}`;
  downloadExcelLink.download = filename;
  downloadExcelLink.classList.remove("is-disabled");
  downloadExcelLink.hidden = false;
};

const renderAgents = () => {
  agentList.innerHTML = groupedAgents
    .map(
      (group) => `
        <section class="agent-group" data-agent-group="${group.id}">
          <h3 class="agent-group__title">${group.name}</h3>
          <div class="agent-group__items">
            ${(group.agents || [])
              .map(
                (agent) => `
                  <button
                    class="agent-tab ${agent.id === selectedAgent?.id ? "is-active" : ""} ${executionState.isRunning ? "is-running" : ""}"
                    type="button"
                    data-agent-id="${agent.id}"
                    ${executionState.isRunning ? "disabled" : ""}
                  >
                    <strong>${agent.icon ? `${agent.icon} ` : ""}${agent.name}</strong>
                    <span>${executionState.isRunning ? "Workflow Running" : agent.short || ""}</span>
                  </button>
                `
              )
              .join("")}
          </div>
        </section>
      `
    )
    .join("");

  if (!selectedAgent && agents.length) {
    selectedAgent = agents[0];
  }
  agentName.textContent = selectedAgent?.name || "No agent available";
  agentDescription.textContent = selectedAgent?.description || "";
  if (prdControls) {
    prdControls.hidden = !isPrdPipelineAgent();
  }
  if (agentPrompt) {
    agentPrompt.closest("label").hidden = isPrdPipelineAgent();
  }
  if (supportsExcelExport(selectedAgent) && isPrdPipelineAgent() && !downloadExcelLink?.getAttribute("href")) {
    showExcelDownloadPending();
  } else if (!supportsExcelExport(selectedAgent)) {
    hideExcelDownload();
  }
  updateExecutionLockUi();
};

const renderCloudModelOptions = () => {
  if (!agentCloudModelInput) {
    return;
  }
  const fallbackModels = [
    { id: "gemini-1.5-flash", name: "gemini-1.5-flash" },
    { id: "gemini-1.5-pro", name: "gemini-1.5-pro" }
  ];
  const options = runtimeCloudModels.length ? runtimeCloudModels : fallbackModels;
  agentCloudModelInput.innerHTML = options
    .map((model, index) => `<option value="${model.id}" ${index === 0 ? "selected" : ""}>${model.name}</option>`)
    .join("");
};

const loadRuntimeOptions = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/runtime/options`);
    if (!response.ok) {
      throw new Error("runtime options unavailable");
    }
    const data = await response.json();
    runtimeProviderOptions = data?.providers || {};
    runtimeCloudModels = data?.providers?.cloud?.models || [];
  } catch (_error) {
    runtimeProviderOptions = {};
    runtimeCloudModels = [];
  }
  renderCloudModelOptions();
  updateAgentProviderUi();
};

const loadAgents = async () => {
  try {
    const response = await fetch(`${API_BASE}/api/agents`);
    if (!response.ok) {
      throw new Error("agent list unavailable");
    }
    const data = await response.json();
    groupedAgents = Array.isArray(data?.grouped_agents) ? data.grouped_agents : [];
    agents = groupedAgents.flatMap((group) => group?.agents || []);
  } catch (_error) {
    groupedAgents = [];
    agents = [];
  }

  selectedAgent = agents[0] || null;
  renderAgents();
};

const formatAgentOutput = (payload) => {
  if (typeof payload?.output === "string" && payload.output.trim()) {
    return payload.output;
  }
  if (typeof payload?.result === "string" && payload.result.trim()) {
    return payload.result;
  }
  if (payload && typeof payload === "object") {
    return JSON.stringify(payload, null, 2);
  }
  return "No output was returned by the server.";
};

const normalizeAgentError = (payload, status) => {
  if (payload?.error?.code && payload?.error?.message) {
    return `${payload.error.code}: ${payload.error.message}`;
  }
  if (typeof payload?.error === "string") {
    return payload.error;
  }
  if (typeof payload?.message === "string" && payload.message.trim()) {
    return payload.message;
  }
  return `Agent request failed with status ${status}`;
};

const runAgent = async () => {
  if (executionState.isRunning) {
    return;
  }
  if (!selectedAgent) {
    agentStatus.textContent = "No agent available";
    return;
  }
  const prompt = isPrdPipelineAgent() ? "run prd pipeline" : agentPrompt.value.trim();
  const provider = agentProviderInput?.value || "cloud";
  const cloudModel = agentCloudModelInput?.value || "gemini-1.5-flash";
  if (!prompt && !isPrdPipelineAgent()) {
    agentOutput.textContent = "Give the agent a request first.";
    return;
  }

  executionState.isRunning = true;
  renderAgents();
  agentStatus.textContent = "Running";
  agentOutput.textContent = "Thinking...";
  latestJsonOutput = "";
  hideExcelDownload();

  try {
    const response = await fetch(`${API_BASE}/api/agents/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(await buildRunPayload(prompt, provider, cloudModel))
    });
    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(normalizeAgentError(data, response.status));
    }
    if (data?.error) {
      throw new Error(normalizeAgentError(data, response.status));
    }

    agentStatus.textContent = data.model || data.status || "Complete";
    latestJsonOutput = JSON.stringify(data, null, 2);
    agentOutput.textContent = formatAgentOutput(data);
    updateExcelDownloadLink(data);
  } catch (error) {
    if (error instanceof Error && error.message.includes("Provide PRD text")) {
      agentStatus.textContent = "Input required";
      agentOutput.textContent = error.message;
    } else if (error instanceof Error) {
      agentStatus.textContent = "Request failed";
      agentOutput.textContent = error.message;
    } else {
      agentStatus.textContent = "Server offline";
      agentOutput.textContent =
        "Could not reach the local agent server. Run this in the project folder:\n\npython agent_server.py\n\nThen make sure Ollama is running if you want real open-source model output.";
    }
    hideExcelDownload();
  } finally {
    executionState.isRunning = false;
    renderAgents();
  }
};

const copyJsonOutput = async () => {
  if (!latestJsonOutput.trim()) {
    agentStatus.textContent = "No JSON to copy";
    return;
  }
  try {
    await navigator.clipboard.writeText(latestJsonOutput);
    const previous = agentStatus.textContent;
    agentStatus.textContent = "JSON copied";
    window.setTimeout(() => {
      agentStatus.textContent = previous;
    }, 1200);
  } catch (_error) {
    agentStatus.textContent = "Copy failed";
  }
};

const updateAgentProviderUi = () => {
  if (!agentProviderInput || !agentCloudModelInput) {
    return;
  }
  const providers = runtimeProviderOptions || {};
  const providerPriority = ["cloud", "openai", "gemini", "grok"];
  const options = providerPriority
    .map((providerId) => providers[providerId])
    .filter((provider) => provider?.enabled !== false);

  agentProviderInput.innerHTML = options
    .map((provider) => `<option value="${provider.id}">${provider.label || provider.id}</option>`)
    .join("");
  if (!agentProviderInput.value && options.length) {
    agentProviderInput.value = options[0].id;
  }

  const isCloud = agentProviderInput.value === "cloud";
  agentCloudModelInput.disabled = !isCloud;
  if (!isCloud) {
    agentStatus.textContent = "Provider unavailable";
    return;
  }
  agentStatus.textContent = "Cloud mode / Gemini";
};

const readFileAsBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = typeof reader.result === "string" ? reader.result : "";
      const marker = "base64,";
      const index = value.indexOf(marker);
      if (index < 0) {
        reject(new Error("Failed to encode file as base64"));
        return;
      }
      resolve(value.slice(index + marker.length));
    };
    reader.onerror = () => reject(new Error("Failed to read selected file"));
    reader.readAsDataURL(file);
  });

const buildRunPayload = async (prompt, provider, cloudModel) => {
  const executionProvider = provider === "local" ? "local" : "cloud";
  const payload = {
    agent: selectedAgent.id,
    input: prompt,
    provider: executionProvider,
    cloud_vendor: executionProvider === "cloud" ? provider : undefined,
    cloud_model: executionProvider === "cloud" ? cloudModel : undefined
  };
  if (!isPrdPipelineAgent()) {
    return payload;
  }

  const prdText = prdTextInput?.value?.trim() || "";
  const selectedFile = prdFileInput?.files?.[0] || null;
  if (!prdText && !selectedFile) {
    throw new Error("Provide PRD text or upload a supported file first.");
  }

  if (prdText) {
    payload.prd_text = prdText;
  } else if (selectedFile) {
    const contentBase64 = await readFileAsBase64(selectedFile);
    payload.uploaded_file = {
      filename: selectedFile.name,
      content_base64: contentBase64
    };
  }
  return payload;
};

window.addEventListener(
  "scroll",
  () => {
    nav.classList.toggle("is-scrolled", window.scrollY > 24);
  },
  { passive: true }
);

menuButton.addEventListener("click", () => {
  const isOpen = menu.classList.toggle("is-open");
  menuButton.setAttribute("aria-expanded", String(isOpen));
});

menu.addEventListener("click", (event) => {
  if (event.target.matches("a")) {
    menu.classList.remove("is-open");
    menuButton.setAttribute("aria-expanded", "false");
  }
});

agentList.addEventListener("click", (event) => {
  if (executionState.isRunning) {
    return;
  }
  const button = event.target.closest("[data-agent-id]");
  if (!button) return;
  selectedAgent = agents.find((agent) => agent.id === button.dataset.agentId) || agents[0] || null;
  resetInputsForAgentSwitch();
  renderAgents();
});

runAgentButton.addEventListener("click", runAgent);
if (agentProviderInput) {
  agentProviderInput.addEventListener("change", updateAgentProviderUi);
}
if (copyJsonButton) {
  copyJsonButton.addEventListener("click", copyJsonOutput);
}

document.querySelector("[data-year]").textContent = new Date().getFullYear();
loadAgents();
loadRuntimeOptions();
