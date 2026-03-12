import os
import sys


def setup_env(force=False):
    if os.path.exists(".env") and not force:
        print("✅ .env file already exists. Skipping setup.")
        print(
            "   (Run 'iron-council setup --force' or use ./dev_start.sh --reconfigure to change settings)"
        )
        return

    current_config = {}
    if force and os.path.exists(".env"):
        print(
            "\n🔄 Reconfiguring... (current .env will be overwritten but defaults preserved)"
        )
        current_config = load_current_env()

    print("\n" + "=" * 50)
    print("IRON COUNCIL - INITIAL CONFIGURATION")
    print("=" * 50)
    print("Detected missing configuration. Let's set up your AI connection.\n")

    print("Choose your AI Provider:")
    print("1. Cloud (OpenAI / Anthropic) - (Unstable/WIP)")
    print("2. Local (Ollama) - (Recommended >= 7B, eg: qwen2.5:14b)")
    print("3. Cloud (Google Gemini) - (Recommended)")

    choice = input("\nEnter choice (1, 2, or 3): ").strip()

    env_content = []

    if choice == "1":
        print("\n[Cloud Setup - OpenAI/Anthropic] - (Unstable/WIP)")
        openai = input("Enter OpenAI API Key (Press Enter to skip): ").strip()
        anthropic = input("Enter Anthropic API Key (Press Enter to skip): ").strip()

        env_content.append(f"LLM_PROVIDER=cloud")
        if openai:
            env_content.append(f"OPENAI_API_KEY={openai}")
        if anthropic:
            env_content.append(f"ANTHROPIC_API_KEY={anthropic}")

    elif choice == "2":
        print("\n[Local Setup - Ollama]")
        default_url = current_config.get(
            "LOCAL_LLM_URL", "http://localhost:11434/api/chat"
        )
        url = input(f"Ollama URL (default: {default_url}): ").strip() or default_url

        default_model = current_config.get("LOCAL_MODEL_NAME", "mistral")
        model = (
            input(f"Model Name (default: {default_model}): ").strip() or default_model
        )

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
        model = (
            input("Model Name (default: gemini-flash-latest): ").strip()
            or "gemini-flash-latest"
        )

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
        print("Invalid choice. Proceeding with existing LLM config if any.")

    # --- Turso DB Setup (Memory Storage) ---
    print("\n[Memory Storage Setup - Turso DB]")
    default_turso_url = current_config.get("TURSO_DB_URL", "")
    default_turso_token = current_config.get("TURSO_DB_TOKEN", "")

    turso_url = input(f"Turso DB URL (default: {default_turso_url}): ").strip() or default_turso_url
    if turso_url.startswith("libsql://"):
        turso_url = turso_url.replace("libsql://", "https://")
    
    turso_token = input(f"Turso DB Token (default: {default_turso_token}): ").strip() or default_turso_token

    if turso_url:
        env_content.append(f"TURSO_DB_URL={turso_url}")
    if turso_token:
        env_content.append(f"TURSO_DB_TOKEN={turso_token}")

    # Add other common defaults if they don't exist in env_content yet
    for key, val in current_config.items():
        if not any(line.startswith(f"{key}=") for line in env_content):
            env_content.append(f"{key}={val}")

    with open(".env", "w") as f:
        f.write("\n".join(env_content) + "\n")

    print("\n✅ Configuration saved to .env")


def load_current_env():
    """Reads the current .env file into a dictionary."""
    config = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, val = line.strip().split("=", 1)
                    config[key] = val
    return config


if __name__ == "__main__":
    force = "--force" in sys.argv
    setup_env(force=force)
