import os
import sys

# Ensure we can import from core by adding root dir to path
sys.path.append(os.getcwd())

from core.agent import IronAgent

def test_prompting():
    print("Initializing General Ares...")
    # Using agent_name as used in the directory structure
    ares = IronAgent("general_ares")
    
    print("\n--- Default System Prompt ---")
    print(ares.construct_system_prompt())
    
    print("\nSimulating Trauma...")
    # Manually setting stats as requested
    ares.soul.dynamic_stats.confidence = 10
    ares.soul.dynamic_stats.paranoia = 90
    
    print("\n--- Traumatized System Prompt ---")
    print(ares.construct_system_prompt())

if __name__ == "__main__":
    test_prompting()
