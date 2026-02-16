import re


def clean_agent_response(text: str, agent_name: str = None) -> str:
    """
    Cleans the agent's response to remove redundant prefixes, markdown markers,
    and meta-dialogue.
    """
    if not text:
        return ""

    text = text.strip()

    # 0. Strip any surviving XML/HTML tags (e.g., <p>, </public_speech>, etc.)
    # Robustified: catches any tag structure </?tagName ... > with support for underscores
    text = re.sub(r"</?(?:[a-z][a-z0-9_]*)\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = text.strip()

    # 1. Strip markdown code blocks (often used by models for 'clean' output)
    if text.startswith("```"):
        # If followed by a newline, assume language identifier
        if "\n" in text:
            # Matches ```python\n
            text = re.sub(r"^```\w*\s*\n", "", text)
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
        name_clean = agent_name.replace("_", " ").replace("-", " ").title()
        short_name = agent_name.split("_")[-1].title()  # Fallback for snake_case
        if short_name == name_clean:
            short_name = None  # Avoid duplicate in regex

        names = [re.escape(name_clean)]
        if short_name:
            names.append(re.escape(short_name))

        # Regex: ^(As |Speaking as )? (**)? (Name|ShortName) (**)? (:)?
        # We use non-capturing groups for efficiency
        name_or = "|".join(names)
        pattern = (
            rf"^\s*(?:(?:As|Speaking as)\s+)?(?:\*\*)?(?:{name_or})(?:\*\*)?\s*:?\s*"
        )
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    # 4. Remove Meta-Dialogue / Recipient Markers
    # Matches: "**To Council:**", "To everyone:", "(Internal Monologue)"
    # Note: We only remove "To X:" at the START of the line.
    text = re.sub(
        r"^\s*(?:\*\*)?To [^:]+:(?:\*\*)?\s*",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Remove internal monologue markers if they appear at start
    text = re.sub(r"^\s*\(Internal Monologue\):?\s*", "", text, flags=re.IGNORECASE)

    # FIX: Truncate Multi-turn Hallucinations
    # If we find a line starting with "Name:" or "Name said:", cut everything after.
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        # Check if line looks like a new speaker: "General Ares:" or "General Ares said:"
        # We need a generic regex for "Name:" pattern but careful not to catch normal text.
        # Strict pattern: Start of line, Capitalized Words, colon.
        if re.match(r"^\s*(?:[A-Z][a-z]+ )+[A-Z][a-z]+:\s*", line):
            # If it matches the agent's OWN name, we skip the line (prefix removal handles this),
            # but if it matches ANOTHER agent, we stop.
            if agent_name and agent_name.replace("_", " ").lower() in line.lower():
                continue  # Skip own name prefix

            # Additional check: Is it one of the known Council members?
            # Hardcoded list for safety or generic pattern? Generic is risky.
            # Let's use the known list from README/Schema if possible, or just strict pattern.
            known_agents = [
                "General Ares",
                "Diplomat Dove",
                "Banker Midas",
                "Analyst Logic",
                "Chairman",
            ]
            if any(ka in line for ka in known_agents):
                break  # STOP processing further lines

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 5. Clean artifacts
    text = re.sub(r"^\*+(?!\s)", "", text, flags=re.MULTILINE)  # Leading asterisks
    text = re.sub(r"(?<!\s)\*+$", "", text, flags=re.MULTILINE)  # Trailing asterisks

    # Final cleanup of quotes/whitespace
    text = text.strip().strip('"').strip("'").strip()

    return text
