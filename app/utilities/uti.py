def clean_text(text):
    """
    Clean text by:
    1. Removing excessive whitespace (tabs, newlines)
    2. Normalizing multiple spaces into single spaces
    3. Joining date patterns (consecutive years) with commas
    """
    if not text:
        return ""
    
    # First normalize all whitespace to single spaces
    cleaned = ' '.join(text.split())
    
    # Fix patterns of consecutive years (like "1995. 1996. 1987")
    import re
    # Pattern to find year-like sequences with periods
    year_pattern = r'(\d{4})\.\s+(\d{4})'
    cleaned = re.sub(year_pattern, r'\1, \2', cleaned)
    
    # Replace any remaining multiple periods with a single one
    cleaned = re.sub(r'\.+', '.', cleaned)
    
    return cleaned.strip()
