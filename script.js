const projects = [
  {
    title: "AI Research Agent",
    category: "AI Agents",
    badge: "Featured",
    description:
      "A multi-step assistant that gathers source material, extracts structured notes, and produces a review-ready brief.",
    tags: ["Agents", "RAG", "Reports"],
    link: "#"
  },
  {
    title: "QA Copilot Workflow",
    category: "Automation",
    badge: "Live",
    description:
      "Converts requirements into test scenarios, browser checks, and bug report drafts with a human approval stage.",
    tags: ["Playwright", "Testing", "QA"],
    link: "#"
  },
  {
    title: "Lead Intelligence Dashboard",
    category: "Dashboards",
    badge: "Case Study",
    description:
      "A lightweight dashboard for tracking prospects, enrichment status, outreach notes, and next actions.",
    tags: ["Dashboard", "CRM", "Automation"],
    link: "#"
  },
  {
    title: "Document RAG Assistant",
    category: "AI Agents",
    badge: "New",
    description:
      "Searches private knowledge, cites relevant snippets, and answers questions from curated business documents.",
    tags: ["RAG", "Embeddings", "Search"],
    link: "#"
  },
  {
    title: "Release Notes Generator",
    category: "Automation",
    badge: "Tool",
    description:
      "Turns commits, issue updates, and QA notes into clean release summaries for product and stakeholder teams.",
    tags: ["GitHub", "LLM", "CI/CD"],
    link: "#"
  },
  {
    title: "Operations Command Center",
    category: "Dashboards",
    badge: "Prototype",
    description:
      "A focused internal tool that centralizes recurring tasks, owners, alerts, and status reporting.",
    tags: ["Internal Tool", "Tasks", "Reports"],
    link: "#"
  }
];

const agents = [
  {
    id: "portfolio_curator",
    name: "Portfolio Curator",
    short: "Turns rough experience into portfolio sections.",
    description:
      "Creates a sharp positioning statement, project summary, and proof points for your portfolio."
  },
  {
    id: "project_case_study",
    name: "Project Case Study Agent",
    short: "Writes case studies from messy project notes.",
    description:
      "Structures a project into problem, solution, architecture, tools, impact, and next improvements."
  },
  {
    id: "qa_strategy",
    name: "QA Strategy Agent",
    short: "Designs test strategy and risk coverage.",
    description:
      "Builds test plans, acceptance coverage, edge cases, automation scope, and release quality gates."
  },
  {
    id: "automation_architect",
    name: "Automation Architect",
    short: "Plans browser, API, and workflow automation.",
    description:
      "Recommends automation flows, tools, selectors, integrations, and CI execution strategy."
  },
  {
    id: "rag_planner",
    name: "RAG Planner",
    short: "Designs document assistant architecture.",
    description:
      "Maps ingestion, chunking, embeddings, retrieval, reranking, citations, and evaluation."
  },
  {
    id: "outreach_writer",
    name: "Outreach Writer",
    short: "Creates concise LinkedIn and email pitches.",
    description:
      "Turns your agent builds into client-facing outreach messages and portfolio captions."
  }
];

const nav = document.querySelector("[data-nav]");
const menu = document.querySelector("[data-menu]");
const menuButton = document.querySelector("[data-menu-button]");
const projectsGrid = document.querySelector("[data-projects]");
const chips = [...document.querySelectorAll("[data-filter]")];
const calendar = document.querySelector("[data-calendar]");
const agentList = document.querySelector("[data-agent-list]");
const agentName = document.querySelector("[data-agent-name]");
const agentDescription = document.querySelector("[data-agent-description]");
const agentPrompt = document.querySelector("[data-agent-prompt]");
const agentOutput = document.querySelector("[data-agent-output]");
const agentStatus = document.querySelector("[data-agent-status]");
const agentProviderInput = document.querySelector("[data-agent-provider]");
const agentCloudModelInput = document.querySelector("[data-agent-cloud-model]");
const agentEncryptedKeyInput = document.querySelector("[data-agent-encrypted-key]");
const runAgentButton = document.querySelector("[data-run-agent]");
const prdTextInput = document.querySelector("[data-prd-text]");
const prdFileInput = document.querySelector("[data-prd-file]");
const prdFrameworkInput = document.querySelector("[data-prd-framework]");
const prdAgentsInput = document.querySelector("[data-prd-agents]");
const prdUseLlmInput = document.querySelector("[data-prd-use-llm]");
const prdStatus = document.querySelector("[data-prd-status]");
const prdOutput = document.querySelector("[data-prd-output]");
const runPrdPipelineButton = document.querySelector("[data-run-prd-pipeline]");
let selectedAgent = agents[0];

const renderProjects = (filter = "All") => {
  const visible = filter === "All" ? projects : projects.filter((project) => project.category === filter);

  projectsGrid.innerHTML = visible
    .map(
      (project) => `
        <article class="project-card">
          <div class="project-card__top">
            <span class="project-card__cat mono">${project.category}</span>
            <span class="project-card__badge">${project.badge}</span>
          </div>
          <h3>${project.title}</h3>
          <p>${project.description}</p>
          <ul>
            ${project.tags.map((tag) => `<li>${tag}</li>`).join("")}
          </ul>
          <a class="project-card__link" href="${project.link}">View project</a>
        </article>
      `
    )
    .join("");
};

const renderCalendar = () => {
  const cells = Array.from({ length: 182 }, (_, index) => {
    const level = (index * 7 + index % 5) % 11;
    const className = level > 8 ? "level-4" : level > 6 ? "level-3" : level > 3 ? "level-2" : level > 1 ? "level-1" : "";
    return `<span class="${className}" title="Activity level ${className || "0"}"></span>`;
  });

  calendar.innerHTML = cells.join("");
};

const renderAgents = () => {
  agentList.innerHTML = agents
    .map(
      (agent) => `
        <button class="agent-tab ${agent.id === selectedAgent.id ? "is-active" : ""}" type="button" data-agent-id="${agent.id}">
          <strong>${agent.name}</strong>
          <span>${agent.short}</span>
        </button>
      `
    )
    .join("");

  agentName.textContent = selectedAgent.name;
  agentDescription.textContent = selectedAgent.description;
};

const runAgent = async () => {
  const prompt = agentPrompt.value.trim();
  const provider = agentProviderInput?.value || "local";
  const cloudModel = agentCloudModelInput?.value || "gemini-1.5-flash";
  const encryptedCloudApiKey = agentEncryptedKeyInput?.value?.trim() || "";
  if (!prompt) {
    agentOutput.textContent = "Give the agent a request first.";
    return;
  }

  runAgentButton.disabled = true;
  agentStatus.textContent = "Running";
  agentOutput.textContent = "Thinking...";

  try {
    const response = await fetch("http://localhost:8787/api/agents/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent: selectedAgent.id,
        input: prompt,
        provider,
        cloud_vendor: provider === "cloud" ? "gemini" : undefined,
        cloud_model: provider === "cloud" ? cloudModel : undefined,
        encrypted_cloud_api_key: provider === "cloud" && encryptedCloudApiKey ? encryptedCloudApiKey : undefined
      })
    });

    if (!response.ok) {
      throw new Error(`Agent server returned ${response.status}`);
    }

    const data = await response.json();
    agentStatus.textContent = data.model || "Complete";
    agentOutput.textContent = data.output;
  } catch (error) {
    agentStatus.textContent = "Server offline";
    agentOutput.textContent =
      "Could not reach the local agent server. Run this in the project folder:\n\npython agent_server.py\n\nThen make sure Ollama is running if you want real open-source model output.";
  } finally {
    runAgentButton.disabled = false;
  }
};

const updateAgentProviderUi = () => {
  if (!agentProviderInput || !agentCloudModelInput || !agentEncryptedKeyInput) {
    return;
  }
  const isCloud = agentProviderInput.value === "cloud";
  agentCloudModelInput.disabled = !isCloud;
  agentEncryptedKeyInput.disabled = !isCloud;
  if (!isCloud) {
    agentStatus.textContent = "Local mode / Ollama";
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

const normalizePipelineError = (payload, status) => {
  if (payload?.error?.code && payload?.error?.message) {
    return `${payload.error.code}: ${payload.error.message}`;
  }
  if (typeof payload?.error === "string") {
    return payload.error;
  }
  return `PRD pipeline request failed with status ${status}`;
};

const getSelectedPrdAgents = () => {
  if (!prdAgentsInput) {
    return [];
  }
  return [...prdAgentsInput.options].filter((option) => option.selected).map((option) => option.value);
};

const runPrdPipeline = async () => {
  if (!prdTextInput || !prdFileInput || !prdFrameworkInput || !prdUseLlmInput || !prdStatus || !prdOutput || !runPrdPipelineButton) {
    return;
  }

  const prdText = prdTextInput.value.trim();
  const selectedFile = prdFileInput.files?.[0] || null;
  if (!prdText && !selectedFile) {
    prdStatus.textContent = "Input required";
    prdOutput.textContent = "Provide PRD text or upload a supported file first.";
    return;
  }

  runPrdPipelineButton.disabled = true;
  prdStatus.textContent = "Running";
  prdOutput.textContent = "Processing PRD...";

  try {
    const body = {
      automation_framework: prdFrameworkInput.value || "playwright",
      use_llm: Boolean(prdUseLlmInput.checked),
      selected_agents: getSelectedPrdAgents()
    };

    if (prdText) {
      body.prd_text = prdText;
    } else if (selectedFile) {
      const contentBase64 = await readFileAsBase64(selectedFile);
      body.uploaded_file = {
        filename: selectedFile.name,
        content_base64: contentBase64
      };
    }

    const response = await fetch("http://localhost:8787/api/prd/pipeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(normalizePipelineError(data, response.status));
    }

    prdStatus.textContent = data.status || "Complete";
    prdOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    prdStatus.textContent = "Failed";
    prdOutput.textContent = error instanceof Error ? error.message : "Unknown PRD pipeline error";
  } finally {
    runPrdPipelineButton.disabled = false;
  }
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

chips.forEach((chip) => {
  chip.addEventListener("click", () => {
    chips.forEach((item) => item.classList.remove("chip--active"));
    chip.classList.add("chip--active");
    renderProjects(chip.dataset.filter);
  });
});

agentList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-agent-id]");
  if (!button) return;
  selectedAgent = agents.find((agent) => agent.id === button.dataset.agentId) || agents[0];
  renderAgents();
});

runAgentButton.addEventListener("click", runAgent);
if (agentProviderInput) {
  agentProviderInput.addEventListener("change", updateAgentProviderUi);
}
if (runPrdPipelineButton) {
  runPrdPipelineButton.addEventListener("click", runPrdPipeline);
}

document.querySelector("[data-year]").textContent = new Date().getFullYear();
renderAgents();
renderProjects();
renderCalendar();
updateAgentProviderUi();
