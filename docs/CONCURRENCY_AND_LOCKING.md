# Concurrency, Locking, and Gating Protocols

## 1. The Two-Gate System

Iron Council v2.0 uses a dual-gate architecture to manage the flow of information (Input) and speech (Output). This ensures that agents are emotionally consistent (Input Gate) and conversationally orderly (Output Gate).

| Gate Name | Type | Direction | Purpose |
| :--- | :--- | :--- | :--- |
| **Physics Gate** | State Barrier | **Input** (Feeling) | Ensures agents "feel" an event before they "react" to it. |
| **The Conch** | Mutex Lock | **Output** (Speaking) | Ensures only one agent speaks at a time to prevent chaos. |

---

## 2. The Input Gate: Reaction Gating

**The Problem (The Psychic Race Condition):**
In a naive async system, Agent A speaks. Agent B's loop wakes up, sees the text, and generates a reply *immediately*. Meanwhile, the slow Physics Engine is still calculating that Agent A's words were actually a deadly insult. Agent B replies politely because it hasn't "felt" the insult yet. 500ms later, the stats update, but it's too late—the context is broken.

**The Solution (`core/ooda.py`):**
The `OODALoop` implements a strict **Refractory Period**.

1.  **Trigger:** When `AGENT_SPEAK` or `WORLD_EVENT` is detected, the loop sets `_waiting_for_physics = True`.
2.  **State:** The agent enters the `FEELING` state (displayed as a pink pulse in the UI).
3.  **Block:** The OODA loop **pauses**. It will NOT proceed to the `DECIDE` phase, effectively silencing the agent.
4.  **Release:** The loop waits for a specific control signal from the `PhysicsSystem`:
    * `PHYSICS_COMPLETE` (for World Events)
    * `AGENT_STATUS` -> `RELATIONSHIP_UPDATE` (for Peer Speech)
5.  **Safety:** A 120-second watchdog timer forces the gate open if the Physics Engine hangs, ensuring the agent doesn't go comatose.

---

## 3. The Output Gate: The Conch

**The Problem (The Hallucination Cascade):**
If two agents speak simultaneously, the chat log becomes nonlinear. Agents reading the log will hallucinate conversations that didn't happen in that order.

**The Solution (`core/heartbeat.py`):**
A strict **Mutex (Mutual Exclusion)** lock called `SpeakingLock`.

* **Acquisition:** Occurs in the `DECIDE` phase. An agent cannot draft a response without holding the lock.
* **Atomicity:** Uses `asyncio.Lock` to strictly serialize acquisition requests.
* **TTL (Time-To-Live):** 180 seconds.
* **Revocation:** The Heartbeat service monitors the lock. If an agent holds it >180s (e.g., an LLM crash), the lock is forcibly "broken" to keep the simulation alive.

---

## 4. Concurrent Processes

While Speech is serialized, most of the system runs in parallel:

1.  **Physics Calculations:** When `AGENT_SPEAK` occurs, the system spawns `N` background threads (one for every listener) to calculate trust updates simultaneously.
2.  **Gamemaster Adjudication:** The "Narrative Verdict" loop runs asynchronously, analyzing batches of messages without blocking the main conversation.
3.  **Drafting:** Agents can `OBSERVE` and `ORIENT` (check stats) while another agent is speaking. They only block when they attempt to `DECIDE` to speak.
4.  **Dreaming:** The Dream Phase (`core/dream.py`) is fully parallel. All agents generate their diaries and update their neural weights (state osmosis) at the same time.