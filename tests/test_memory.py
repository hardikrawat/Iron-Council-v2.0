from memory.store import SubjectiveMemory
import os
import shutil

def test_subjective_memory():
    # Clean up existing DB for testing
    db_path = "test_db"
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    
    memory = SubjectiveMemory(db_path=db_path)
    
    # Save memories for Ares
    memory.save_memory("Ares", "I am the God of War and I value strength.", "proud")
    memory.save_memory("Ares", "Battle is where I find my purpose.", "determined")
    
    # Save memory for Dove
    memory.save_memory("Dove", "I dream of a peaceful world without conflict.", "hopeful")
    
    # Recall memories for Ares
    ares_memories = memory.recall_memories("Ares", "What do I value?")
    print(f"Ares memories: {ares_memories}")
    
    # Recall memories for Dove
    dove_memories = memory.recall_memories("Dove", "What are my dreams?")
    print(f"Dove memories: {dove_memories}")
    
    # Cross-check: Ares should NOT remember Dove's dream
    cross_check = memory.recall_memories("Ares", "peaceful world")
    print(f"Ares recall for 'peaceful world': {cross_check}")
    
    # Verification assertions
    assert len(ares_memories) > 0
    assert any("strength" in m for m in ares_memories)
    assert len(dove_memories) > 0
    assert any("peaceful" in m for m in dove_memories)
    assert all("peaceful" not in m for m in cross_check)
    
    print("\nVerification successful! Ares does not remember Dove's dreams.")

    # Cleanup
    if os.path.exists(db_path):
        shutil.rmtree(db_path)

if __name__ == "__main__":
    test_subjective_memory()
