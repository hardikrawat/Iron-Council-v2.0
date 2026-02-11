import re

def clean_agent_response(text: str, agent_name: str = None) -> str:
    """
    Cleans the agent's response to remove redundant prefixes, markdown markers, 
    and meta-dialogue.
    """
    if not text:
        return ""

    text = text.strip()

    # 1. Strip markdown code blocks (often used by models for 'clean' output)
    if text.startswith("```"):
        # If followed by a newline, assume language identifier
        if '\n' in text:
            # Matches ```python\n
            text = re.sub(r'^```\w*\s*\n', '', text)
        else:
            # Inline block or no newline, just remove markers
            text = text[3:].strip()
            
        # Remove closing ```
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()

    # 2. Strip quotes (standard/triple)
    if text.startswith('"""') and text.endswith('"""'):
        text = text[3:-3].strip()
    elif text.startswith('**"') and text.endswith('"**'):
        text = text[3:-3].strip()
    elif text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    elif text.startswith("'") and text.endswith("'"):
        text = text[1:-1].strip()

    # 3. Remove Name Prefixes
    # Matches: "General Ares:", "**General Ares**:", "As General Ares:", "Ares:"
    if agent_name:
        name_clean = agent_name.replace('_', ' ').replace('-', ' ').title()
        short_name = agent_name.split('_')[-1].title() # Fallback for snake_case
        if short_name == name_clean:
            short_name = None # Avoid duplicate in regex
            
        names = [re.escape(name_clean)]
        if short_name:
            names.append(re.escape(short_name))
            
        # Regex: ^(As |Speaking as )? (**)? (Name|ShortName) (**)? (:)?
        # We use non-capturing groups for efficiency
        name_or = "|".join(names)
        pattern = fr"^\s*(?:(?:As|Speaking as)\s+)?(?:\*\*)?(?:{name_or})(?:\*\*)?\s*:?\s*"
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

    # 4. Remove Meta-Dialogue / Recipient Markers
    # Matches: "**To Council:**", "To everyone:", "(Internal Monologue)"
    # Note: We only remove "To X:" at the START of the line.
    text = re.sub(r'^\s*(?:\*\*)?To [^:]+:(?:\*\*)?\s*', '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # Remove internal monologue markers if they appear at start
    text = re.sub(r'^\s*\(Internal Monologue\):?\s*', '', text, flags=re.IGNORECASE)

    # 5. Clean artifacts
    text = re.sub(r'^\*+(?!\s)', '', text, flags=re.MULTILINE) # Leading asterisks
    text = re.sub(r'(?<!\s)\*+$', '', text, flags=re.MULTILINE) # Trailing asterisks
    
    # Final cleanup of quotes/whitespace
    text = text.strip().strip('"').strip("'").strip()
    
    return text
