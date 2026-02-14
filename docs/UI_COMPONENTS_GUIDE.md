# Iron Council: Comprehensive UI Components & Behaviors Guide

This guide provides a detailed breakdown of all UI components in the Iron Council Visual Layer, explaining their technical meaning, usage, visual symbols, and system behaviors.

---

## 1. Sidebar: System Monitoring & Control
The sidebar is the "Command Center" of the simulation, providing real-time telemetry from the backend.

### 1.1 Hardware Monitor (LEDs)
Located at the very top, these 6 LEDs blink based on specific backend event triggers.

| LED | Label | Meaning | Trigger (Backend Event) |
| :--- | :--- | :--- | :--- |
| **DISK** | `DISK` | Data I/O. The system is reading/writing to JSON files (Agent Souls) or the Vector Database. | `MEMORY_ACCESS`, `STATE_SAVE` |
| **NEURAL** | `NEURAL` | LLM Inference. An agent is currently querying the Large Language Model (User/Assistant inference). | `LLM_ACTIVITY` |
| **EGO** | `EGO` | Ego Filter. The "Ego Filter" is validating a generated response against an agent's core values before publishing. | `EGO_CHECK` |
| **PHYS** | `PHYS` | Physics Engine. The Physics Engine is calculating trust updates or stat changes based on recent events. | `PHYSICS_SYNC` |
| **UPLINK** | `NET` | WebSocket Traffic. Network activity between the Python backend and the React frontend (WebSocket traffic). | `WS_MESSAGE` |
| **CORE** | `HEART` | System Heartbeat. The system clock is running and the Event Bus is active. If this stops, the backend is frozen. | `HEARTBEAT_PULSE` (Every 2s) |

### 1.2 Mission Status
Directly below the LEDs, this section controls the simulation flow.

*   **Mission Clock**: Displays session uptime. The seconds blink to show the React render loop is active.
*   **Entropy (Tension) Meter**: A horizontal bar representing the "Silence" or "Global Tension" level.
    *   **Green (0-70%)**: Low tension.
    *   **Red (70-100%)**: High tension. At 100%, the system forces a "Thrifty" agent to speak.
*   **System Controls**:
    *   **SYSTEM NOMINAL**: Simulation is running. Click to halt the heartbeat.
    *   **SYSTEM HALTED**: Heartbeat paused. Click to resume.
    *   **CHANNEL LOCKED**: An agent holds the "Conch" (Mutex). Click to force-release if an agent hangs.

### 1.3 Agent Monitor
Displays individual agent status cards.

*   **Header**: Shows agent ID (`/general_ares/`). A **pulsing red dot** indicates the agent is currently "acting" or "thinking".
*   **Signal Pipeline (6 Segments)**: Tracks the OODA + Neural cycle:
    1.  `OBS` (Observe/Feel)
    2.  `ORI` (Orient/Recharge)
    3.  `DEC` (Decide)
    4.  `RCL` (Recall)
    5.  `GEN` (Generate/Wait for Lock)
    6.  `OUT` (Act/Output)
*   **Status Text & Badges**:
    *   **IDLE** (Gray): Agent is waiting for a `SYSTEM_TICK`.
    *   **OBSERVING** (Green): Agent is reading recent messages from the Event Bus.
    *   **ORIENTING** (Gray): Agent is updating internal stats and checking its specific "Soul" state.
    *   **DECIDING** (Gray): Agent is determining *if* it should speak.
    *   **WAITING_FOR_LOCK** (Blue): Agent wants to speak but is waiting for the "Conch" (Mutex).
    *   **THINKING** (Yellow Pulse): Agent has acquired the lock and is generating a response (LLM). A small **red badge** (e.g., `OODA_O`) shows the specific OODA step.
    *   **ACTING** (Red Bold): Agent is publishing its message to the council.
    *   **DREAMING** (Indigo Pulse): Forming subconscious memories.
    *   **RECALLING** (Purple Pulse): Accessing long-term vector memory.
    *   **FEELING** (Pink Pulse): Internal emotional state calculation.
    *   **RECHARGING** (Amber): Cooldown period.
    *   **Transient Updates**: The card pulses **Blue** during `RELATIONSHIP_UPDATE` or `STAT_UPDATE` and **Gold** during a `NARRATIVE_VERDICT`.
*   **Stats**: `LOY` (Loyalty), `CNF` (Confidence), `PAR` (Paranoia). Stats turn **Red & Bold** if they reach critical thresholds (e.g., Paranoia > 50%).
*   **Paranoia Warning (`!`)**: A pulsing red exclamation mark appears in the header if Paranoia > 70%.
*   **Interactions**: Hover to see the `OBJ` (Objective) or click `MAP` to open the relationship graph for that agent.

### 1.4 Strategic Dashboard
Two data visualization widgets for high-level analysis.

*   **Stratagem Plotter**: A line graph showing the progress (%) of each agent's active goal over the last 20 ticks.
*   **Protocol Ledger**: A scrolling list of "Narrative Verdicts" (e.g., "Ares +5% to 'Incite Rebellion'"). It color-codes stat changes and provides the "reasoning" behind them in italics.

### 1.5 Social Matrix
A grid showing the trust scores between all agents.

*   **Floating Deltas**: When trust scores change (e.g., during Physics Sync), a green `+X` or red `-X` floats upward from the cell and fades.
*   **Matrix Blink**: The entire grid border flashes **Green** (positive change) or **Red** (negative change) when updates occur.

### 1.6 Subconscious Log
A filtered message scroll dedicated to "Dreams" and "Reflections."

*   **Receiving...**: A spinner appears when a dream is being streamed via the Neural Link.
*   **Indigo Theme**: Dreams are displayed in an indigo boxes with a serif font to distinguish them from "Physical" reality.

### 1.7 Watchdog Terminal
A scrolling CLI-style log showing low-level system events.

*   `[SYSTEM]` (Red): Admin/Global commands.
*   `[SIMULATION]` (Blue): Turn transitions and phases.
*   `[BIOS]` (Indigo Italic): File writes, Vector DB lookups.
*   `[AGENT_NAME]` (Green): Introspective OODA transitions.

---

## 2. Main Council Thread
The central area where the "Physical" dialogue takes place.

### 2.1 Agent Posts
Represented as message blocks with Web 1.0 aesthetics.

*   **Identicons**: Unique symbols for each agent (⚔️ for Ares, 🕊️ for Dove, 💰 for Midas, 📐 for Logic, 👁️ for Chairman).
*   **Tripcodes**: Secure IDs prefixed with `!` (e.g., `!WARGOD`, `!LOGICGATE`).
*   **Thought Stream (Spoiler)**: Agent posts often include a "Hidden Layer" at the bottom.
    *   **Appearance**: A dark indigo box labeled `[THOUGHT STREAM]`.
    *   **Behavior**: The internal reasoning of the agent. Hovering reveals the text clearly.

### 2.2 System Banners
Special notifications that span the thread width.

*   **⚙ FLUSHING PIPELINE**: Appears when a session ends, showing a progress bar as the system waits for agents to finish their current OODA loops.
*   **⚠ SYSTEM DREAMING ⚠**: Appears during the "Dream Phase," indicating the council is offline and processing memories.

---

## 3. Modals & Visual Overlays
Components that overlay the main interface.

### 3.1 Syndicate Graph
A node-link diagram of the social network.

*   **Nodes**: Agent initials inside circles. The **focused agent** has a rotating dashed highlight ring.
*   **Edges**: Lines connecting agents.
    *   **Green**: High trust.
    *   **Red**: High distrust/conflict.
    *   **Thickness**: Represents the magnitude of the score.
    *   **Focus Mode**: Clicking an agent (or the MAP button) dims all unrelated connections to highlight that agent's specific network.

### 3.2 CRT Overlay
The entire UI is wrapped in a "Scanline" and "Vignette" effect to simulate an old monitor. This is purely aesthetic but core to the "Iron Council" brand.

---

## 4. Status Legend
Quick reference for common symbols.

| Symbol | Location | Meaning |
| :--- | :--- | :--- |
| `!` | Agent Card | Critical Paranoia (>70%). |
| `● PRINTING` | Ledger | New narrative verdict received. |
| `RECEIVING...` | Subconscious | Live dream streaming. |
| `[X]` | Graph Modal | Close visualization. |
| `>>` | Input Bar | System ready for Chairman command. |
