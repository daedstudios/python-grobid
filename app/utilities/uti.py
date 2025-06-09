import os
import logging
import requests
from typing import Union, Tuple


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('grobid_processor')

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

def download_file(url: str, destination_path: str, doc_dir: str = None) -> Tuple[bool, str]:
    """
    Download a file from a URL to the specified destination path.
    If the file already exists, it won't be downloaded again.
    
    Args:
        url (str): The URL of the file to download
        destination_path (str): The local path where the file should be saved
        doc_dir (str, optional): The document directory. If provided, it will be created.
        
    Returns:
        Tuple[bool, str]: (Success status, Error message if any)
    """
    # Create document directory if provided
    if doc_dir:
        os.makedirs(doc_dir, exist_ok=True)
        logger.info(f"Created/verified document directory: {doc_dir}")
    
    # Check if file already exists
    if os.path.exists(destination_path):
        logger.info(f"File already exists at {destination_path}, skipping download")
        return True, ""
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    
    try:
        logger.info(f"Downloading file from {url}")
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        with open(destination_path, "wb") as f:
            f.write(response.content)
            
        logger.info(f"File downloaded successfully to {destination_path}")
        return True, ""
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP error downloading file: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error downloading file: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except requests.exceptions.Timeout as e:
        error_msg = f"Timeout error downloading file: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Error downloading file: {str(e)}"
        logger.error(error_msg)
        return False, error_msg