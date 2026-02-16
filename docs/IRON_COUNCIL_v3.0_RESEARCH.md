# Project IRON COUNCIL v3.0: The Evolving Brain

**A Research Initiative in Artificial General Intelligence (AGI) focusing on Subjective Reality, Neuroplasticity, and Digital Consciousness.**

> "True identity is not a prompt in a context window. It is a bias in the neural weights. Agents in v3.0 do not just 'act' like General Ares—they become him through continuous parameter evolution."

---

## Documentation

For a deep dive into the system's design, including the Event-Driven Architecture, Physics Engine, and Heartbeat mechanism, please see [ARCHITECTURE.md](docs/ARCHITECTURE.md).

## The v3.0 Philosophy: From Simulation to Life

In traditional multi-agent systems (v1/v2), "identity" is fragile—it relies on text prompts ("You are General Ares") that can be overridden or forgotten by the model. This creates "Identity Drift," where agents hallucinate or revert to being generic assistants.

**Iron Council v3.0** solves this by replicating the biological structure of consciousness:

1.  **Subjective Reality:** Agents never see the "God View" transcript. They process the world exclusively through a first-person lens ("I said," not "Ares said").
2.  **Neuroplasticity (The "Soul" Weights):** We do not share one brain. Each agent possesses a unique **LoRA Adapter (Low-Rank Adaptation)** that is fine-tuned nightly.
3.  **Confirmation Bias:** Agents develop genuine psychological inertia. If General Ares spends a week being paranoid, his neural weights update to physically prevent him from trusting others easily—creating true, stubborn personality traits.

---

## Architecture: The "Bicameral" Engine

The v3.0 architecture splits the agent into two distinct systems: The **Software Mind** (Real-time OODA Loop) and the **Hardware Brain** (Offline Training Loop).

### 1. The Day Cycle: Subjective Reality (Software)
* **The "I" Shift:** The transcript is dynamically rewritten before inference. General Ares never reads "General Ares: Attack." He reads "**YOU:** Attack." This forces the model into an ego-centric perspective.
* **Inner Monologue:** Before speaking, agents execute a hidden `(THOUGHT)` block, analyzing the situation based on their current stats.
* **Stat Osmosis:** Emotional shifts in the narrative (e.g., "I feel betrayed") are instantly converted into math (Trust -15) by the Physics Engine.

### 2. The Night Cycle: Neuroplasticity (Hardware)
* **The Dream:** Agents process the day's events, generating a "Diary" that solidifies their bias.
* **The Sleep (Training):** Instead of just saving text, the system performs a **Continuous Learning Step**.
    * **Input:** The day's internal monologues and decisions.
    * **Process:** Optimized fine-tuning run (using Unsloth/Peft).
    * **Output:** A unified `ares_v{day}.safetensors` adapter.
* **Result:** The next morning, Ares acts paranoid *without* being prompted, because his neural pathways now favor paranoid tokens.

---

## Technical Stack (v3.0)

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Inference Engine** | **Ollama / vLLM** | Serves the Base Model + Hot-swappable LoRA Adapters. |
| **Training Engine** | **Unsloth (PyTorch)** | Ultra-fast fine-tuning during the "Sleep" phase. |
| **Base Model** | `Llama-3-8B` / `Mistral` | The shared "reptilian brain" (Language & Logic). |
| **Agent Brains** | **LoRA Adapters** | ~50MB files representing individual "Souls" (Biases). |
| **Memory** | **Turso DB** | Vector storage for subjective episodic recall. |
| **Orchestrator** | Python 3.11+ | Manages the Event Bus, Physics, and Training triggers. |

---

## Key Features

### 1. Identity Persistence via Weight Updates
In v2, if you removed the system prompt, Ares became a chatbot.
In v3, if you remove the system prompt, **Ares is still Ares.** His vocabulary, tone, and biases are baked into the model's parameters. He literally *cannot* speak like Diplomat Dove.

### 2. The "Subjective Filter"
The system no longer feeds raw chat logs to the agents.
* **Raw Log:** `Ares: No. Dove: Why?`
* **Ares Sees:** `YOU: No. Dove: Why?`
* **Dove Sees:** `Ares: No. YOU: Why?`

This creates a hard cognitive boundary between "Self" and "Other," solving the issue of agents speaking for one another.

### 3. Evolving Confirmation Bias
As the simulation runs, agents become "set in their ways."
* **Day 1:** Ares is suspicious of Midas (Prompt-based).
* **Day 10:** Ares has trained on 10 days of suspicion. Even if Midas donates 1,000 gold, Ares's model predicts that it is a "trap" because his weights have overfit to Midas=Threat.

---

## Roadmap to v3.0

### Phase 1: The Conscious Core (Software Implementation)
- [ ] **Subjective Context:** Implement the "YOU" replacement logic in `core/ooda.py`.
- [ ] **Stream of Consciousness:** Enforce `<INTERNAL_MONOLOGUE>` tags in all prompts.
- [ ] **Dream Osmosis:** Update `dream.py` to output JSON stat updates, not just text.

### Phase 2: The Training Pipeline (Hardware Integration)
- [ ] **Dataset Collector:** Create a pipeline to harvest `(Prompt, Response)` pairs from daily sessions.
- [ ] **The "Sleep" Script:** Integrate `unsloth` to perform quick LoRA fine-tuning on the day's data.
- [ ] **Adapter Manager:** Update `core/llm.py` to dynamically load `adapter={agent_name}` during inference.

---

## Idea Preservation & Timestamp

> **Note:** This document outlines original research and future implementation plans for Iron Council v3.0.

- **Author:** Hardik Rawat
- **Timestamp:** 2026-02-12T18:13:12+05:30 (IST)
- **Concept:** Subjective Reality & Neuroplasticity in Event-Driven Multi-Agent Systems
- **Status:** Research / Pre-Alpha
- **Statement:** The methodology of using continuous nightly LoRA fine-tuning ("Sleep/Dream") to engrave agent bias into model weights ("Neuroplasticity") is a core innovation of this project.
