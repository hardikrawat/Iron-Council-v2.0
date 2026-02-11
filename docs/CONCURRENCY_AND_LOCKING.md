# Concurrency, Locking, and LLM Usage Analysis

## 1. Concurrency Model: Can Agents use LLM at the same time?

**The short answer is: YES, but with strict controls.**

The system is designed as an asynchronous event-driven architecture (`core/event_bus.py`). Each agent runs as an independent `OODALoop` task.

### Where LLM Usage is Parallel (Concurrent)
1.  **The Dream Phase**: At the end of a session, all agents generate their diaries and hidden agendas simultaneously. `core/dream.py` does *not* use the central lock.
2.  **Physics Calculations**: When an event occurs, the `PhysicsSystem` spawns background threads (`asyncio.to_thread`) to calculate impacts and relationship updates using the LLM. This happens concurrently with other agents' `Observe` and `Orient` cycles.
3.  **Drafting vs. Speaking**: While one agent is *speaking* (sending bytes to the websocket), another agent might be *drafting* a thought or updating its internal state, provided it doesn't need "The Conch" yet.

### Where LLM Usage is Serialized (Locked)
*   **The Act Phase (Speaking)**: The actual generation of public speech is strictly serialized. An agent MUST acquire "The Conch" (Lock) before it can invoke the LLM to generate a spoken response.
    *   *Reference*: `core/ooda.py` lines 272 (Acquire) -> 303 (Speak/LLM).

## 2. The Lock System: "The Conch"

The "Lock" you referred to is implemented as `SpeakingLock` in `core/heartbeat.py`.

*   **Type**: Mutex (Mutual Exclusion) using `asyncio.Lock`.
*   **Purpose**: 
    1.  **Line-Taking**: Prevents agents from talking over each other.
    2.  **Context Consistency**: Ensures that when an agent speaks, the conversation state is stable (no one else is changing the topic mid-generation).
*   **Mechanism**:
    *   **Acquisition**: An agent attempts to acquire the lock in the `Decide` phase.
    *   **TTL (Time-To-Live)**: The lock has a 60-second hardware expiry. If an agent "dies" or the LLM hangs while holding the lock, the `Heartbeat` forcibly revokes it to prevent a deadlock.
    *   **Renewal**: Agents can renew the lock if their thought process takes longer than expected, up to 2x the TTL.

---

## 3. Critical Findings & Architectural Bugs

During the analysis, two significant concurrency issues were identified that threaten the "Loyalty to Architecture".

### Bug A: The Persistence of Ignorance (Physics Race Condition)
**Severity**: High
**Location**: `core/ooda.py` vs `core/physics_system.py`

*   **The Issue**: The OODA loop correctly gates itself when a `WORLD_EVENT` occurs (waiting for `PHYSICS_COMPLETE`), but it **fails to gate itself** when an `AGENT_SPEAK` event occurs.
*   **The Consequence**: 
    1.  Agent A speaks (betraying Agent B).
    2.  `PhysicsSystem` starts calculating the "Trust Fall" for Agent B (LLM call takes ~3s).
    3.  concurrently, Agent B's OODA loop receives the message, Decides, acquires the Lock, and **Acts**.
    4.  **Result**: Agent B responds *before* the Trust Fall is applied. Agent B is unaware of the betrayal until *after* they have already spoken.

### Bug B: The Bottleneck of Memory
**Severity**: Medium
**Location**: `core/ooda.py` (Line 281)

*   **The Issue**: `recall_memories()` is called **inside** the locked critical section (after acquiring the Conch).
*   **The Consequence**: The agent holds the "talking stick" while it is silently rummaging through its memories. If recall is slow (vector search + potential reranking), it blocks the entire council from speaking, even though no output is being generated yet.
*   **Fix**: Move `recall_memories` to the `Decide` phase (before lock acquisition).
