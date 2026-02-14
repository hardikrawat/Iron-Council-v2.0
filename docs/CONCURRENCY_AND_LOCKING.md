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
    *   **TTL (Time-To-Live)**: The lock has a **180-second (3 minute)** hardware expiry. If an agent "dies" or the LLM hangs while holding the lock, the `Heartbeat` forcibly revokes it to prevent a deadlock.
    *   **Renewal**: Agents can renew the lock if their thought process takes longer than expected, up to **4x the TTL** (with original acquisition tracking).

---

## 3. Resolved Architectural Issues

The following issues were identified and resolved in the v2.0 development cycle to ensure architectural integrity.

### [FIXED] Bug A: The Persistence of Ignorance (Physics Race Condition)
**Status**: RESOLVED (Implemented in `core/ooda.py`)

*   **The Issue**: The OODA loop correctly gated itself when a `WORLD_EVENT` occurred, but it previously failed to gate itself when an `AGENT_SPEAK` event occurred, leading to reactions before trust was updated.
*   **The Fix**: `OODALoop` now explicitly triggers `_waiting_for_physics = True` upon detecting `AGENT_SPEAK` from peers. It waits for `PHYSICS_COMPLETE` or `AGENT_STATUS` (RELATIONSHIP_UPDATE) before proceeding to the `Decide` phase. It includes a **120-second safety timeout** to prevent indefinite hangs in case of worker failure.
*   *Reference*: `core/ooda.py` lines 84-90 (Gating) and 230-234 (Safety Timeout).

### [FIXED] Bug B: The Bottleneck of Memory
**Status**: RESOLVED (Implemented in `core/ooda.py`)

*   **The Issue**: `recall_memories()` was previously called inside the locked critical section, blocking the entire council while an agent performed slow vector searches.
*   **The Fix**: `recall_memories` has been moved to the `Decide` phase, occurring **before** the agent attempts to acquire "The Conch". The agent now performs internal reflection while the floor is still open to others.
*   *Reference*: `core/ooda.py` lines 332-358.
