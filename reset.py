import json
import os
import shutil

# The Default Data: Exact starting JSON for all 4 agents
DEFAULT_STATES = {
    "general_ares": {
        "name": "General Ares",
        "archetype": "General",
        "base_model": "mistral-large",
        "core_values": ["Strength", "Hierarchy", "Decisiveness"],
        "dynamic_stats": {
            "confidence": 85,
            "paranoia": 10,
            "loyalty_to_chairman": 40,
            "stress_level": 15
        },
        "relationships": {
            "Diplomat Dove": -40,
            "Banker Midas": 20,
            "Analyst Logic": 0
        }
    },
    "diplomat_dove": {
        "name": "Diplomat Dove",
        "archetype": "Diplomat",
        "base_model": "mistral-large",
        "core_values": ["Peace", "Cooperation", "Nuance"],
        "dynamic_stats": {
            "confidence": 60,
            "paranoia": 40,
            "loyalty_to_chairman": 80,
            "stress_level": 10
        },
        "relationships": {
            "General Ares": -30,
            "Banker Midas": 10
        }
    },
    "banker_midas": {
        "name": "Banker Midas",
        "archetype": "Banker",
        "base_model": "mistral-large",
        "core_values": ["Wealth", "Stability", "Leverage"],
        "dynamic_stats": {
            "confidence": 90,
            "paranoia": 60,
            "loyalty_to_chairman": 20,
            "stress_level": 50
        },
        "relationships": {
            "General Ares": 20,
            "Diplomat Dove": 20
        }
    },
    "analyst_logic": {
        "name": "Analyst Logic",
        "archetype": "Analyst",
        "base_model": "mistral-large",
        "core_values": ["Truth", "Data", "Efficiency"],
        "dynamic_stats": {
            "confidence": 100,
            "paranoia": 0,
            "loyalty_to_chairman": 100,
            "stress_level": 0
        },
        "relationships": {}
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
