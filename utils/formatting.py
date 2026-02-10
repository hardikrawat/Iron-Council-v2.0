import re

def clean_agent_response(text: str, agent_name: str = None) -> str:
    """
    Cleans the agent's response to remove redundant prefixes, markdown markers, 
    and meta-dialogue.
    """
    if not text:
        return ""

    # 1. Strip triple/double quotes if the LLM wrapped the whole thing
    text = text.strip()
    if text.startswith('"""') and text.endswith('"""'):
        text = text[3:-3].strip()
    elif text.startswith('**"') and text.endswith('"**'):
        text = text[3:-3].strip()
    elif text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()

    # 2. Remove redundant name prefix (e.g., "General Ares: ", "Ares: ")
    # This matches common LLM behaviors where they prepend their name.
    if agent_name:
        # Normalize agent name for matching (underscores to spaces, handle "Name Surname")
        possible_prefixes = [
            f"{agent_name}:",
            f"{agent_name.replace('_', ' ').title()}:",
            f"{agent_name.split('_')[-1].title()}:", # Just "Ares:" if name is "general_ares"
        ]
        
        # Also handle cases where the name is in bold
        bold_prefixes = [f"**{p}**" for p in possible_prefixes]
        all_prefixes = possible_prefixes + bold_prefixes
        
        for prefix in all_prefixes:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
                break

    # 3. Remove common meta-dialogue markers (including internal ones on new lines)
    # Matches: **To Council:**, **To the council:**, **To Banker Midas:**, etc.
    text = re.sub(r'^\*\*To [^:]+:\*\*\s*', '', text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r'^\*To [^:]+:\*\s*', '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # 4. Remove leading/trailing formatting artifacts like *** or **
    # Also handle them if they appear at start of lines inside the message
    text = re.sub(r'^\*+(?!\s)', '', text, flags=re.MULTILINE)
    text = re.sub(r'(?<!\s)\*+$', '', text, flags=re.MULTILINE)
    
    # Remove leading/trailing quotes again in case they were inside prefixes
    text = text.strip().strip('"').strip("'").strip()
    
    return text
