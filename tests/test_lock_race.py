import sys
import os
import time
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from core.heartbeat import SpeakingLock

# Configure logging to verify error messages
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

def TestLockRace():
    print("\n--- TEST: Lock Race Condition ---")
    
    # Setup: Lock with short TTL
    lock = SpeakingLock(ttl_seconds=2.0)
    
    # 1. Agent A acquires the lock
    assert lock.acquire("Agent_A")
    print("[PASS] Agent_A acquired lock.")
    
    # 2. Simulate Latency > TTL
    print("... Simulating 2.1s LLM latency ...")
    time.sleep(2.1)
    
    # 3. Agent B attempts to acquire (The Theft)
    # With the FIX, this should automatically expire Agent_A's lock and give it to B.
    success_b = lock.acquire("Agent_B")
    if success_b:
        print("[PASS] Agent_B successfully acquired the expired lock (Zombie Check working).")
    else:
        print("[FAIL] Agent_B failed to acquire expired lock!")
        return

    # 4. Agent A finishes generation and tries to release (The Crash)
    # This simulates the critical race condition moment.
    # Expectation: Agent A should NOT be able to release B's lock.
    # Expectation: Should log a CRITICAL ERROR but not raise exception.
    
    print("Agent_A attempting to release (Should trigger ERROR log)...")
    lock.release("Agent_A")
    
    # 5. Verification
    if lock.owner == "Agent_B":
        print("[PASS] Lock owner is still Agent_B.")
    else:
        print(f"[FAIL] Lock owner is {lock.owner} (Should be Agent_B).")

    # Clean up
    lock.release("Agent_B")
    print("--- Test Complete ---\n")

if __name__ == "__main__":
    TestLockRace()
