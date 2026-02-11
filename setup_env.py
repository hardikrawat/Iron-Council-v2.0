
import os
import sys

def setup_env(force=False):
    if os.path.exists(".env") and not force:
        print("✅ .env file already exists. Skipping setup.")
        print("   (Run with --force or use ./start_visual_council.sh --reconfigure to change settings)")
        return

    if force and os.path.exists(".env"):
        print("\n🔄 Reconfiguring... (current .env will be overwritten)")

    print("\n" + "="*50)
    print("IRON COUNCIL - INITIAL CONFIGURATION")
    print("="*50)
    print("Detected missing configuration. Let's set up your AI connection.\n")

    print("Choose your AI Provider:")
    print("1. Cloud (OpenAI / Anthropic) - Best for reasoning")
    print("2. Local (Ollama) - Free, private, runs on your machine")
    print("3. Cloud (Google Gemini) - Fast, generous free tier")
    
    choice = input("\nEnter choice (1, 2, or 3): ").strip()
    
    env_content = []
    
    if choice == "1":
        print("\n[Cloud Setup - OpenAI/Anthropic]")
        openai = input("Enter OpenAI API Key (Press Enter to skip): ").strip()
        anthropic = input("Enter Anthropic API Key (Press Enter to skip): ").strip()
        
        env_content.append(f"LLM_PROVIDER=cloud")
        if openai:
            env_content.append(f"OPENAI_API_KEY={openai}")
        if anthropic:
            env_content.append(f"ANTHROPIC_API_KEY={anthropic}")
            
    elif choice == "2":
        print("\n[Local Setup - Ollama]")
        url = input("Ollama URL (default: http://localhost:11434/api/chat): ").strip() or "http://localhost:11434/api/chat"
        model = input("Model Name (e.g. mistral, llama3, neural-chat): ").strip() or "mistral"
        
        env_content.append(f"LLM_PROVIDER=local")
        env_content.append(f"LOCAL_LLM_URL={url}")
        env_content.append(f"LOCAL_MODEL_NAME={model}")
        
        # Override individual agents to use this local model
        env_content.append(f"GENERAL_ARES_MODEL={model}")
        env_content.append(f"DIPLOMAT_DOVE_MODEL={model}")
        env_content.append(f"BANKER_MIDAS_MODEL={model}")
        env_content.append(f"ANALYST_LOGIC_MODEL={model}")

    elif choice == "3":
        print("\n[Cloud Setup - Google Gemini]")
        gemini = input("Enter Google Gemini API Key: ").strip()
        model = input("Model Name (default: gemini-2.0-flash): ").strip() or "gemini-2.0-flash"
        
        env_content.append(f"LLM_PROVIDER=cloud")
        if gemini:
            env_content.append(f"GEMINI_API_KEY={gemini}")
            # Map agents to Gemini for convenience
            env_content.append(f"GENERAL_ARES_MODEL={model}")
            env_content.append(f"DIPLOMAT_DOVE_MODEL={model}")
            env_content.append(f"BANKER_MIDAS_MODEL={model}")
            env_content.append(f"ANALYST_LOGIC_MODEL={model}")
        else:
            print("⚠️ No API key provided for Gemini.")

    else:
        print("Invalid choice. Creating empty .env")

    with open(".env", "w") as f:
        f.write("\n".join(env_content))
    
    print("\n✅ Configuration saved to .env")

if __name__ == "__main__":
    force = "--force" in sys.argv
    setup_env(force=force)
