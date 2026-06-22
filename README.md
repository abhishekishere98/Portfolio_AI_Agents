# AI Agent Portfolio - Easy User Guide

This folder contains two things:

1. A portfolio website.
2. A small AI agent system that can run on your own computer.

The website shows your work. The Agent Lab inside the website lets people try small AI agents, like a Portfolio Curator, QA Strategy Agent, and RAG Planner.

## Files In This Folder

- `index.html` - the main website page.
- `styles.css` - the design and colors.
- `script.js` - the website actions, project filters, and Agent Lab buttons.
- `agents.json` - the list of agents and what each agent should do.
- `agent_server.py` - the local server that runs the agents.
- `prd_pipeline.py` - the enterprise PRD to QA pipeline.
- `ENTERPRISE_RAG_FRAMEWORK.md` - detailed architecture for the PRD pipeline.
- `PRD_PIPELINE_QUICKSTART.md` - quick way to test the PRD pipeline.
- `HOSTING.md` - simple hosting guide.

## What You Need

You need these three things:

- A browser, like Chrome or Edge.
- Python 3.11 or newer.
- Ollama, if you want to use a real open-source AI model.

Ollama is an app that lets your computer run open-source AI models locally.

Download Ollama here:

```text
https://ollama.com/download
```

## Quick Start

Follow these steps in order.

### Step 1: Open This Folder

Open PowerShell in this project folder:

```powershell
C:\Users\abhis\OneDrive\Documents\AI Agents
```

### Step 2: Install One AI Model

Run this command:

```powershell
ollama pull qwen3:8b
```

This downloads the AI model. It may take some time because the file is large.

### Step 3: Configure Cloud Providers (Encrypted Keys)

Generate encrypted API keys (one time per key):

```powershell
python encrypt_api_key.py
```

The script is standalone and asks for:

- your plain cloud API key
- your encryption secret (input hidden)

Copy encrypted output into `cloud_providers.json` (`api_key_encrypted` fields).

Preferred setup (no runtime shell env needed): add the same secret directly in `cloud_providers.json`:

```json
{
  "api_key_encryption_secret": "your_long_random_secret",
  "vendors": [
    {
      "id": "gemini",
      "models": [
        {
          "id": "gemini-1.5-flash",
          "api_key_encrypted": "..."
        }
      ]
    }
  ]
}
```

Optional fallback (legacy): set `API_KEY_ENCRYPTION_SECRET` in shell before starting server.

The UI no longer accepts direct key input. Cloud model options are populated from `cloud_providers.json`.

Encrypted token format expected by backend (`api_key_encrypted` in config):

- Base64 URL-safe encoded bytes (`urlsafe_b64encode`)
- Binary payload layout:
  - `salt` (16 bytes)
  - `nonce` (16 bytes)
  - `ciphertext` (N bytes, API key length)
  - `mac` (32 bytes, HMAC-SHA256)
- Key derivation: `PBKDF2-HMAC-SHA256(secret, salt, 200000, dklen=32)`
- Ciphertext generation: each plaintext byte is XORed with derived key byte and nonce byte (both repeated cyclically)
- Integrity check: `HMAC_SHA256(derived_key, salt + nonce + ciphertext)` must match `mac`

### Step 4: Start The Agent Server

```powershell
python agent_server.py
```

You should see something like:

```text
Agent server running at http://localhost:8787
```

Keep this PowerShell window open. If you close it, the agents will stop working.

### Step 5: Open The Website

Open this file in your browser:

```text
index.html
```

Then scroll to the **Agent Lab** section.

### Step 6: Try An Agent

1. Click an agent name.
2. Type your request.
3. Click **Run agent**.

Example request:

```text
I built an AI tool that reads a product requirement document and creates test cases.
Make this into a portfolio project.
```

## If Something Does Not Work

### Problem: The website opens, but the agent says server offline

Fix:

```powershell
python agent_server.py
```

Make sure the server is still running.

### Problem: `python` is not recognized

Install Python from:

```text
https://www.python.org/downloads/
```

During installation, tick the checkbox that says **Add Python to PATH**.

### Problem: `ollama` is not recognized

Install Ollama from:

```text
https://ollama.com/download
```

Then close PowerShell, open it again, and retry:

```powershell
ollama pull qwen3:8b
```

### Problem: The AI answer is slow

That is normal on laptops. Local AI models need CPU, RAM, or GPU power.

Try a smaller model:

```powershell
ollama pull mistral:7b
```

Then run:

```powershell
$env:OLLAMA_MODEL = "mistral:7b"
python agent_server.py
```

## Agents In This Project

There are now two agent systems:

1. Simple portfolio agents in the Agent Lab.
2. Enterprise PRD pipeline agents for PRD analysis, review, test design, and automation design.

Read this for the enterprise pipeline:

```text
PRD_PIPELINE_QUICKSTART.md
```

Read this for the full architecture:

```text
ENTERPRISE_RAG_FRAMEWORK.md
```

### Portfolio Curator

Use this when you have rough experience and want it written nicely for your portfolio.

Example:

```text
I know Python, Playwright, and AI agents. Help me write my portfolio intro.
```

### Project Case Study Agent

Use this when you want to explain a project clearly.

Example:

```text
I made a chatbot using local documents. Write a case study for it.
```

### QA Strategy Agent

Use this when you want test cases or a testing plan.

Example:

```text
Create a QA plan for a shopping website with login, cart, and payment.
```

### Automation Architect

Use this when you want to automate a repeated task.

Example:

```text
I want to automate checking job posts every morning and save useful ones.
```

### RAG Planner

Use this when you want an AI assistant that answers from documents.

Example:

```text
Plan a RAG app that can answer questions from PDF files.
```

### Outreach Writer

Use this when you want LinkedIn posts, cold DMs, or emails.

Example:

```text
Write a LinkedIn post about my AI test case generator project.
```

## How To Edit Your Portfolio

### Change Your Name

Open `index.html`.

Search for:

```text
Abhishek
```

Replace it with your full name.

### Change Email

Search for:

```text
hello@example.com
```

Replace it with your email.

### Change Projects

Open `script.js`.

Find this line:

```javascript
const projects = []
```

Edit the project titles, descriptions, tags, and links.

### Change Agent Instructions

Open `agents.json`.

Each agent has a `prompt`. That is the instruction given to the AI model.

Example:

```json
"prompt": "You are a QA architect. Create test cases..."
```

Change the prompt if you want the agent to behave differently.

## Simple Mental Model

Think of this project like this:

```text
Browser website
    |
    v
script.js sends request
    |
    v
agent_server.py receives request
    |
    v
Ollama runs open-source AI model
    |
    v
Answer comes back to website
```

## Safety Rules

- Do not put passwords or secret keys into the Agent Lab.
- Do not expose Ollama directly on the public internet.
- If you host this online, protect the backend with login, rate limits, and CORS rules.
- Keep private documents private unless you understand what the agent will do with them.

## Enterprise PRD Pipeline

Use this when you want to paste a PRD extract and generate:

- Epics
- User stories
- Acceptance criteria
- Demo points
- Personas
- Component test cases
- E2E test cases
- Unit test suggestions
- PACT contract test suggestions
- Playwright or Selenium automation ideas

Start the server:

```powershell
python agent_server.py
```

API endpoint:

```text
POST http://localhost:8787/api/prd/pipeline
```

Simple request:

```json
{
  "prd_text": "Paste PRD here",
  "automation_framework": "playwright",
  "use_llm": true
}
```

If Ollama is not ready yet, use:

```json
"use_llm": "false"
```

## Next Step

After it works locally, read `HOSTING.md` to learn how to put the website online.
