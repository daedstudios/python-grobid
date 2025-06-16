from typing import Dict, List, Optional, Any
import uuid
import logging
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('note_extractor')

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def extract_notes_from_tei(tei_file_path: str, paper_summary_id: str) -> List[Dict[str, Any]]:
    """
    Extract all notes from a TEI XML file
    
    This function extracts all types of notes from a TEI XML file, including:
    - Footnotes (place="foot")
    - Endnotes 
    - Marginal notes
    - Other types of notes
    
    It preserves all attributes like xml:id, place, and n (note number).
    It also extracts the content of the notes, including nested elements like
    references to bibliography items.
    
    Args:
        tei_file_path (str): Path to the TEI XML file
        paper_summary_id (str): ID of the paper summary
        
    Returns:
        list: Extracted notes data with all attributes and content
    """
    logger.info(f"Extracting notes from {tei_file_path}")
    
    try:
        with open(tei_file_path, 'r', encoding='utf-8') as tei:
            soup = BeautifulSoup(tei, 'lxml-xml')
    except Exception as e:
        logger.error(f"Error opening or parsing TEI file: {str(e)}")
        return []
    
    # Find all note elements
    notes = soup.find_all('note')
    logger.info(f"Found {len(notes)} notes in the document")
    
    results = []
    
    for note in notes:
        try:
            note_data = {
                "id": str(uuid.uuid4()),
                "paper_summary_id": paper_summary_id,
                "created_at": datetime.datetime.now().isoformat(),
                "updated_at": datetime.datetime.now().isoformat()
            }
            
            # Extract attributes
            xml_id = note.get('xml:id', None)
            note_data['xml_id'] = xml_id
            
            place = note.get('place', None)
            note_data['place'] = place
            
            n = note.get('n', None)
            note_data['note_number'] = n
            
            # Extract text content
            text_content = ""
            p_elements = note.find_all('p')
            
            if p_elements:
                # Join the text from all p elements
                for p in p_elements:
                    # Extract text and clean up whitespace
                    p_text = ' '.join(p.get_text().split())
                    text_content += p_text + " "
            else:
                # If no p elements, just get all text
                text_content = ' '.join(note.get_text().split())
            
            note_data['content'] = text_content.strip()
            
            # Extract references if any
            refs = []
            ref_elements = note.find_all('ref')
            for ref in ref_elements:
                ref_data = {
                    "type": ref.get('type', None),
                    "target": ref.get('target', None),
                    "text": ref.get_text().strip()
                }
                refs.append(ref_data)
            
            if refs:
                note_data['references'] = refs
            
            # Extract HTML content for rich display
            # Get the inner HTML including tags but strip the outer note tag
            html_content = ""
            for element in note.children:
                html_content += str(element)
            note_data['html_content'] = html_content.strip()
            
            results.append(note_data)
            
        except Exception as e:
            logger.error(f"Error processing note {xml_id if 'xml_id' in locals() else 'unknown'}: {str(e)}")
    
    return results

def add_notes_to_supabase(notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Add extracted notes to Supabase
    
    Args:
        notes (list): List of note data dictionaries
        
    Returns:
        dict: Result of the operation
    """
    if not notes:
        logger.warning("No notes to add to Supabase")
        return {"success": False, "message": "No notes to add", "count": 0}
    
    try:
        # Insert notes into Supabase
        response = supabase.table("PaperNotes").insert(notes).execute()
        
        return {
            "success": True,
            "message": f"Successfully added {len(notes)} notes to Supabase",
            "count": len(notes),
            "data": response.data
        }
    except Exception as e:
        error_details = str(e)
        logger.error(f"Error adding notes to Supabase: {error_details}")
        
        # Print complete error details for debugging
        print(f"Supabase error details: {error_details}")
        
        return {
            "success": False, 
            "message": f"Error: {error_details}", 
            "count": 0,
            "error": error_details
        }

def process_notes(tei_file_path: str, paper_summary_id: str) -> Dict[str, Any]:
    """
    Process and add notes from a TEI file to Supabase
    
    Args:
        tei_file_path (str): Path to the TEI XML file
        paper_summary_id (str): ID of the paper summary
        
    Returns:
        dict: Result of the operation
    """
    # Extract notes from the TEI file
    notes = extract_notes_from_tei(tei_file_path, paper_summary_id)
    
    if not notes:
        return {"success": False, "message": "No notes extracted", "count": 0}
    
    # Add notes to Supabase
    result = add_notes_to_supabase(notes)
    
    return result

# Example usage (if run directly)
if __name__ == "__main__":
    # For testing
    test_file = "./test_out/test.grobid.tei.xml"
    test_paper_id = "12345678-1234-5678-1234-567812345678"
    
    if os.path.exists(test_file):
        result = process_notes(test_file, test_paper_id)
        print(json.dumps(result, indent=2))
    else:
        print(f"Test file {test_file} not found")