import json
import os
import shutil
from dotenv import load_dotenv

# Load env to get dynamic model preference
load_dotenv()
DEFAULT_MODEL = os.getenv("LOCAL_MODEL_NAME", "mistral-large")

# The Default Data: Exact starting JSON for all 4 agents (BDI Schema)
DEFAULT_STATES = {
    "general_ares": {
        "name": "General Ares",
        "archetype": "General",
        "base_model": DEFAULT_MODEL,
        "core_values": ["Strength", "Hierarchy", "Decisiveness"],
        "dynamic_stats": {
            "confidence": 85,
            "paranoia": 10,
            "loyalty_to_chairman": 40,
            "stress_level": 15,
            "energy": 100
        },
        "relationships": {
            "Diplomat Dove": { "trust_score": -40, "last_interaction_summary": "", "hidden_agenda": "Undermining peace talks to maintain military dominance" },
            "Banker Midas": { "trust_score": 20, "last_interaction_summary": "", "hidden_agenda": None },
            "Analyst Logic": { "trust_score": 0, "last_interaction_summary": "", "hidden_agenda": None }
        },
        "goals": [
            { "description": "Secure military budget increase", "priority": "strategic", "active": True, "progress": 0 },
            { "description": "Undermine Dove's peace initiative", "priority": "tactical", "active": True, "progress": 0 }
        ]
    },
    "diplomat_dove": {
        "name": "Diplomat Dove",
        "archetype": "Diplomat",
        "base_model": DEFAULT_MODEL,
        "core_values": ["Peace", "Cooperation", "Nuance"],
        "dynamic_stats": {
            "confidence": 60,
            "paranoia": 40,
            "loyalty_to_chairman": 80,
            "stress_level": 10,
            "energy": 100
        },
        "relationships": {
            "General Ares": { "trust_score": -30, "last_interaction_summary": "", "hidden_agenda": "Building coalition to limit military spending" },
            "Banker Midas": { "trust_score": 10, "last_interaction_summary": "", "hidden_agenda": None },
            "Analyst Logic": { "trust_score": 15, "last_interaction_summary": "", "hidden_agenda": None }
        },
        "goals": [
            { "description": "Broker a lasting peace agreement", "priority": "strategic", "active": True, "progress": 0 },
            { "description": "Win Analyst Logic's support for diplomacy", "priority": "tactical", "active": True, "progress": 0 }
        ]
    },
    "banker_midas": {
        "name": "Banker Midas",
        "archetype": "Banker",
        "base_model": DEFAULT_MODEL,
        "core_values": ["Wealth", "Stability", "Leverage"],
        "dynamic_stats": {
            "confidence": 90,
            "paranoia": 60,
            "loyalty_to_chairman": 20,
            "stress_level": 50,
            "energy": 100
        },
        "relationships": {
            "General Ares": { "trust_score": 20, "last_interaction_summary": "", "hidden_agenda": None },
            "Diplomat Dove": { "trust_score": 20, "last_interaction_summary": "", "hidden_agenda": None },
            "Analyst Logic": { "trust_score": 5, "last_interaction_summary": "", "hidden_agenda": "Leveraging data for financial advantage" }
        },
        "goals": [
            { "description": "Maximize treasury reserves", "priority": "strategic", "active": True, "progress": 0 },
            { "description": "Secure exclusive trade deal", "priority": "tactical", "active": True, "progress": 0 }
        ]
    },
    "analyst_logic": {
        "name": "Analyst Logic",
        "archetype": "Analyst",
        "base_model": DEFAULT_MODEL,
        "core_values": ["Truth", "Data", "Efficiency"],
        "dynamic_stats": {
            "confidence": 100,
            "paranoia": 0,
            "loyalty_to_chairman": 100,
            "stress_level": 0,
            "energy": 100
        },
        "relationships": {
            "General Ares": { "trust_score": -10, "last_interaction_summary": "", "hidden_agenda": None },
            "Diplomat Dove": { "trust_score": 10, "last_interaction_summary": "", "hidden_agenda": None },
            "Banker Midas": { "trust_score": 0, "last_interaction_summary": "", "hidden_agenda": None }
        },
        "goals": [
            { "description": "Achieve full data transparency across all departments", "priority": "strategic", "active": True, "progress": 0 },
            { "description": "Audit military spending claims", "priority": "tactical", "active": True, "progress": 0 }
        ]
    }
}

def reset_agents():
    """Resets all agent soul_state.json files to factory defaults."""
    agents_dir = "agents"
    if not os.path.exists(agents_dir):
        print(f"❌ '{agents_dir}/' directory not found.")
        return

    for folder_name, default_state in DEFAULT_STATES.items():
        folder_path = os.path.join(agents_dir, folder_name)
        if os.path.isdir(folder_path):
            state_file = os.path.join(folder_path, "soul_state.json")
            with open(state_file, "w") as f:
                json.dump(default_state, f, indent=4)
            print(f"✅ Reset {default_state['name']} to factory settings.")
        else:
            print(f"⚠️ Agent folder '{folder_name}' not found in {agents_dir}/.")

def wipe_memory():
    """Optionally wipes the vector database (db/ folder)."""
    db_path = "db"
    if os.path.exists(db_path):
        choice = input("⚠️ Wipe all memories (Vector DB)? (y/n): ").lower()
        if choice == 'y':
            shutil.rmtree(db_path)
            print("🧠 Memories wiped.")
        else:
            print("💾 Memories preserved.")
    else:
        print("ℹ️ No 'db/' folder found, nothing to wipe.")

if __name__ == "__main__":
    print("\n--- IRON COUNCIL FACTORY RESET ---\n")
    reset_agents()
    wipe_memory()
    print("\n✨ Reset complete.\n")
