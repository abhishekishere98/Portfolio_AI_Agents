# Hosting Guide - Easy Version

This guide explains how to put your portfolio online and how to run the AI agents.

Read this slowly. You do not need to understand everything on day one.

## First Important Idea

This project has two parts:

1. Website
2. Agent backend

The website is easy to host.

The agent backend is harder because it needs an AI model running somewhere.

## Simple Diagram

```text
Visitor opens your portfolio website
          |
          v
Website sends a question to your agent backend
          |
          v
Backend sends the question to an open-source AI model
          |
          v
AI model sends an answer back
          |
          v
Visitor sees the answer on the website
```

## Best Beginner Plan

Start with this:

- Host only the website online.
- Run the agent backend locally on your laptop when you want to demo it.

This is cheaper, easier, and safer.

Later, when you are ready, host the backend on a server.

## Option 1: Host Only The Website

This is the easiest option.

Use one of these:

- Vercel
- Netlify
- GitHub Pages
- Cloudflare Pages

Recommended for beginners: **Vercel**.

### How To Host On Vercel

1. Create a GitHub account if you do not have one.
2. Create a new GitHub repository.
3. Upload these files:
   - `index.html`
   - `styles.css`
   - `script.js`
   - `agents.json`
   - `README.md`
   - `HOSTING.md`
4. Go to:

```text
https://vercel.com/
```

5. Sign in with GitHub.
6. Click **Add New Project**.
7. Select your repository.
8. Use these settings:
   - Framework Preset: Other
   - Build Command: leave empty
   - Output Directory: `.`
9. Click **Deploy**.

Now your portfolio website is online.

Important: the Agent Lab will not fully work online yet unless your backend is also hosted.

## Option 2: Local Agent Demo

This is best for learning and interviews.

Run this on your laptop:

```powershell
ollama pull qwen3:8b
python agent_server.py
```

Then open:

```text
index.html
```

This proves that your agents are real.

## Option 3: Public Agent Demo

Use this only after the local demo works.

For a public demo, you need:

- A server.
- An open-source AI model.
- Your Python backend.
- HTTPS.
- Basic protection so people cannot abuse your server.

### Easy Server Choices

You can rent a server from:

- RunPod
- Lambda Labs
- Vast.ai
- DigitalOcean
- AWS
- Google Cloud
- Azure

For open-source AI models, a GPU server is better. CPU servers can work, but they may be slow.

## Tools To Use

### For Local AI

Use **Ollama**.

Why:

- Easy to install.
- Runs open-source models.
- Good for local demos.
- Works with models like Qwen, Llama, Mistral, and DeepSeek distilled models.

Good beginner model:

```powershell
ollama pull qwen3:8b
```

Smaller model:

```powershell
ollama pull mistral:7b
```

### For Production AI

Use **vLLM** when you need a real public server with more speed.

Simple meaning:

- Ollama is easier.
- vLLM is stronger for production.

Do not start with vLLM if you are a beginner. Start with Ollama.

### For RAG

RAG means the AI answers using your own documents.

Use:

- ChromaDB for simple local projects.
- Qdrant for bigger hosted projects.

Example use case:

```text
Upload PDF files.
AI reads them.
User asks questions.
AI answers using those PDF files.
```

### For Backend

This project currently uses:

```text
agent_server.py
```

This is good for learning.

Later, upgrade to:

- FastAPI
- Flask

FastAPI is a good next step.

## What Not To Do

Do not put Ollama directly on the internet.

Bad idea:

```text
Public website -> Ollama directly
```

Better idea:

```text
Public website -> Your backend -> Ollama or vLLM
```

Why?

Because your backend can add safety:

- Login
- Rate limits
- Request limits
- Logging
- CORS protection

## Beginner Hosting Roadmap

### Level 1: Local Only

Use this while learning.

```text
Open index.html locally
Run python agent_server.py locally
Run Ollama locally
```

### Level 2: Website Online, Agents Local

Use this for portfolio sharing.

```text
Website hosted on Vercel
Agents run only on your laptop during demos
```

### Level 3: Website And Agents Online

Use this when you want anyone to try your agents.

```text
Website on Vercel
Backend on a server
Model on Ollama or vLLM
HTTPS enabled
Rate limits enabled
```

## Minimum Safety Checklist

Before making agents public, check these:

- Do not allow unlimited requests.
- Do not allow very large prompts.
- Do not store passwords in logs.
- Do not expose private documents.
- Do not let public users run shell commands.
- Add a simple login or secret API key.
- Restrict your backend to your website domain.

## Common Questions

### Can I host the whole thing on Vercel?

You can host the website on Vercel.

Do not host the open-source AI model on Vercel. AI models need long-running compute, and Vercel serverless is not made for that.

### Can I use only free tools?

For local demo, yes:

- Ollama is free.
- The website is static.
- Python is free.

For public AI agents, you may need to pay for a server.

### Which model should I use first?

Use:

```text
qwen3:8b
```

If it is too slow, try:

```text
mistral:7b
```

### What is the easiest final setup?

For now:

```text
Vercel for website
Laptop + Ollama for agent demos
```

Later:

```text
Vercel for website
GPU server for backend and model
```

## Useful Links

- Ollama: `https://ollama.com/`
- Ollama API docs: `https://docs.ollama.com/api`
- vLLM docs: `https://docs.vllm.ai/`
- Vercel: `https://vercel.com/`
- GitHub Pages: `https://pages.github.com/`
