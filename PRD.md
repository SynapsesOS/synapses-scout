This is a high-stakes addition to your OS. **Synapse-Scout** isn't just a search tool; it is the **Sensory Cortex** of your system.

Below is a professional, technical **Product Requirements Document (PRD)** specifically structured for an agent like **Claude Code** to consume and execute. It focuses on modularity, high performance (M3 Pro optimized), and the "Deterministic" philosophy you’ve established.

---

# 📄 PRD: Project Synapse-Scout

**Status:** Draft | **Owner:** Itachi | **Target:** Multi-Modal Knowledge Acquisition Layer

## 1. Product Overview & Objectives

**Synapse-Scout** is the third fundamental leg of Synapses-OS. Its goal is to provide a unified interface for extracting real-time information from the external world (Web, YouTube, Documents) and distilling it into structured, deterministic context fragments.

**Key Objectives:**

* **Zero-Noise Extraction:** Convert messy HTML/Media into clean, LLM-ready Markdown/JSON.
* **Multimodal Reach:** Support for Web Search, YouTube Transcripts, and Document Parsing (PDF/Docx).
* **Deterministic Routing:** Eliminate "hallucinated searching" by providing the agent with exact data paths.
* **Local-First Efficiency:** Maximize local processing (M3 Pro) for transcription and summarization to reduce the "Token Tax."

---

## 2. Core Feature Requirements

### A. The "Searcher" (Discovery)

* **Function:** Query the live web.
* **Base Package:** [Tavily Python SDK](https://www.google.com/search?q=https://github.com/tavily/tavily-python) or [Exa-py](https://github.com/exa-labs/exa-py).
* **Requirement:** Must return "Context-Rich" results (content snippets, not just links).

### B. The "Extractor" (Web & Docs)

* **Function:** Turn any URL or File into structured text.
* **Base Package:** [Firecrawl](https://github.com/mendableai/firecrawl) (for Web) and [Docling](https://github.com/DS4SD/docling) (for PDFs/Docs).
* **Requirement:** Must output **Github-Flavored Markdown** to preserve structural intent (headers, tables).

### C. The "Auralist" (Video & Audio)

* **Function:** Extract intelligence from YouTube/Media.
* **Base Package:** [yt-dlp](https://github.com/yt-dlp/yt-dlp) for metadata/downloading; [Whisper.cpp](https://github.com/ggerganov/whisper.cpp) for local transcription.
* **Requirement:** Automatic extraction of YouTube auto-generated captions if available, falling back to local Whisper transcription if not.

### D. The "Distiller" (Intelligence Layer)

* **Function:** Summarize and "Fragment" the raw data.
* **Base Package:** [Instructor](https://github.com/jxnl/instructor) (for structured Pydantic outputs).
* **Requirement:** Convert a 2000-word blog post or 1-hour video into a **300-word Synapse Fragment** with defined metadata tags.

---

## 3. Technical Stack (Base Foundation)

| Layer | Recommended Technology |
| --- | --- |
| **Language** | **Python 3.11+** (for AI orchestration) or **Go** (for the high-speed crawler wrapper). |
| **Search API** | **Tavily** (Primary) / **DuckDuckGo-Search** (Local/Free fallback). |
| **Web Scraping** | **Crawl4AI** (Best for adaptive LLM extraction). |
| **Local Inference** | **Ollama** (Running Gemma 2B or Qwen 2.5 for local distillation). |
| **Schema** | **Pydantic** (To ensure deterministic JSON outputs). |

---

## 4. Architecture & Integration

Synapse-Scout must interface with the existing **Thinking** and **Memory** legs:

1. **Request:** Thinking Leg says: *"I need to know the latest pricing for Apple M3 chips."*
2. **Scout Action:** Scout searches Tavily $\rightarrow$ identifies 3 top blogs $\rightarrow$ crawls via Firecrawl.
3. **Distillation:** Scout uses a local model to extract a JSON object: `{ "item": "M3 Pro", "price": "$1999", "source": "URL" }`.
4. **Memory Integration:** Scout sends this JSON to the **Memory Leg** to be stored in the Neo4j Graph.

---

## 5. Implementation Roadmap for Claude Code

### **Phase 1: The Universal Scraper (Week 1)**

* Implement `ScoutClient` class.
* Integrate `Firecrawl` for web-to-markdown conversion.
* Integrate `Docling` for local PDF/Docx processing.

### **Phase 2: The Media Pipeline (Week 1.5)**

* Wrap `yt-dlp` to fetch YouTube metadata and transcripts.
* Set up a local `Whisper.cpp` worker to handle audio files.

### **Phase 3: The Distillation Engine (Week 2)**

* Define Pydantic schemas for `SynapseFragment`.
* Implement a "Triage" logic: If text > 1000 words, run local summarization before passing to Synapses-OS.