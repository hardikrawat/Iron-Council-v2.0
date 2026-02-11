# Iron Council: UI Indicators Guide

This document explains the meanings of the various status indicators, LEDs, and metrics visible in the Iron Council "Visual Layer" (UI).

## 1. Hardware Monitor (The 6 LEDs)
Located in the sidebar, these 6 LEDs provide real-time feedback on the system's backend activity.

| LED | Label | Color | Trigger (Backend Event) | Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **CORE** | HEART | Red Pulse | `HEARTBEAT` (Every 2s) | The system clock is running and the Event Bus is active. If this stops, the backend is frozen. |
| **DISK** | DISK | Amber | `MEMORY_ACCESS`, `STATE_SAVE` | The system is reading/writing to JSON files (Agent Souls) or the Vector Database. |
| **NEURAL** | NEURAL | Cyan | `LLM_ACTIVITY` | An agent is currently querying the Large Language Model (User/Assistant inference). |
| **EGO** | EGO | Fuchsia | `EGO_CHECK` | The "Ego Filter" is validating a generated response against an agent's core values before publishing. |
| **PHYS** | PHYS | Blue | `PHYSICS_SYNC` | The Physics Engine is calculating trust updates or stat changes based on recent events. |
| **UPLINK** | UPLINK | Green | `WS_MESSAGE` | Network activity between the Python backend and the React frontend (WebSocket traffic). |

---

## 2. Agent Monitor
Each agent card in the sidebar displays their current cognitive state.

### Status Indicators
- **IDLE** (Gray): Agent is waiting for a `SYSTEM_TICK`.
- **OBSERVING** (Green): Agent is reading recent messages from the Event Bus.
- **ORIENTING** (Gray): Agent is updating internal stats and checking its specific "Soul" state.
- **DECIDING** (Gray): Agent is determining *if* it should speak.
- **WAITING_FOR_LOCK** (Blue): Agent wants to speak but is waiting for the "Conch" (Mutex).
- **THINKING** (Yellow Pulse): Agent has acquired the lock and is generating a response (LLM).
- **ACTING** (Red Bold): Agent is publishing its message to the council.

### OODA Loop Bars
The 4 small bars below the agent ID represent the **OODA Loop** phases:
1.  **O**bserve
2.  **O**rient
3.  **D**ecide
4.  **A**ct

They light up (`Indigo`) as the agent progresses through the loop.

### Paranoia Warning
- A pulsing Red **!** appears if an agent's `Paranoia` stat exceeds **70%**.

---

## 3. Mission Control (Top Sidebar)

### Mission Clock
- Displays the session uptime.
- **Seconds** blink to indicate the React app's render cycle is healthy.

### Entropy (Tension) Meter
- **Green → Red Gradient**: Displays the "Global Tension" or "Silence" level.
- **Behavior**: Rises when the council is silent.
- **Threshold**: At **70%**, it turns Red and glows. If it hits 100%, the system forces a "Thrifty" agent to speak to break the silence.

### System Status
- **SYSTEM NOMINAL** (Green): The Heartbeat is running.
- **SYSTEM HALTED** (Red Pulse): The Heartbeat is paused (Manual Toggle or Dream Phase).
- **CHANNEL LOCKED** (Red Pulse): An agent holds the "Conch" and is speaking. Clicking this allows you to "Force Halt" the lock if stuck.

---

## 4. Watchdog Terminal (Bottom Sidebar)
- **SYSTEM** (Red): Admin/Chairman commands.
- **SIMULATION** (Blue): Turn processing and Dream Phase events.
- **AGENT** (Green): Agent introspection logs.
- **BIOS** (Indigo/Italic): Low-level system events (Memory/Disk IO).
