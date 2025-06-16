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
logger = logging.getLogger('figure_extractor')

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def extract_figures_from_tei(tei_file_path: str, paper_summary_id: str) -> List[Dict[str, Any]]:
    """
    Extract all figure elements from a TEI XML file
    
    This function extracts all figures from a TEI XML file, including:
    - Figures with complete metadata (head, label, figDesc)
    - Figures with only graphic elements
    - Figures with partial metadata
    
    It preserves all attributes like xml:id and extracts graphic coordinates
    when available.
    
    Args:
        tei_file_path (str): Path to the TEI XML file
        paper_summary_id (str): ID of the paper summary
        
    Returns:
        list: Extracted figures data with all attributes and content
    """
    logger.info(f"Extracting figures from {tei_file_path}")
    
    try:
        with open(tei_file_path, 'r', encoding='utf-8') as tei:
            soup = BeautifulSoup(tei, 'lxml-xml')
    except Exception as e:
        logger.error(f"Error opening or parsing TEI file: {str(e)}")
        return []
    
    # Find all figure elements
    figures = soup.find_all('figure')
    logger.info(f"Found {len(figures)} figures in the document")
    
    results = []
    
    for i, figure in enumerate(figures):
        try:
            figure_data = {
                "id": str(uuid.uuid4()),
                "paper_summary_id": paper_summary_id,
                "created_at": datetime.datetime.now().isoformat(),
                "updated_at": datetime.datetime.now().isoformat(),
                "order_index": i  # Keep track of the original order
            }
            
            # Extract xml:id attribute
            xml_id = figure.get('xml:id') or ""
            figure_data['xml_id'] = xml_id
            
            # Extract head (title) if present
            head = figure.find('head')
            if head:
                figure_data['title'] = head.get_text().strip()
            else:
                # If no head, try to infer a title from figDesc or xml:id
                if figure.find('figDesc'):
                    desc_text = figure.find('figDesc').get_text().strip()
                    # If figDesc starts with "Figure X:", extract that as the title
                    if desc_text.lower().startswith('figure'):
                        parts = desc_text.split(':', 1)
                        if len(parts) > 1:
                            figure_data['title'] = parts[0].strip()
                        else:
                            figure_data['title'] = ""
                    else:
                        figure_data['title'] = ""
                elif xml_id and xml_id.startswith('fig_'):
                    # Create a title from the xml:id (e.g., "fig_1" becomes "Figure 1")
                    fig_num = xml_id.replace('fig_', '')
                    if fig_num.isdigit():
                        figure_data['title'] = f"Figure {fig_num}"
                    else:
                        figure_data['title'] = ""
                else:
                    figure_data['title'] = ""
            
            # Extract label if present
            label = figure.find('label')
            if label:
                figure_data['label'] = label.get_text().strip()
                figure_data['figure_number'] = label.get_text().strip()
            else:
                # Try to extract figure number from title or xml:id
                if figure_data['title'] and 'figure' in figure_data['title'].lower():
                    # Extract number from title (e.g., "Figure 1" -> "1")
                    parts = figure_data['title'].lower().replace('figure', '').strip()
                    if parts and parts[0].isdigit():
                        figure_data['figure_number'] = parts.strip()
                    else:
                        figure_data['figure_number'] = ""
                elif xml_id and xml_id.startswith('fig_'):
                    # Extract number from xml:id (e.g., "fig_1" -> "1")
                    fig_num = xml_id.replace('fig_', '')
                    if fig_num.isdigit():
                        figure_data['figure_number'] = fig_num
                    else:
                        figure_data['figure_number'] = ""
                else:
                    figure_data['figure_number'] = ""
                figure_data['label'] = figure_data['figure_number']
            
            # Extract figure description if present
            fig_desc = figure.find('figDesc')
            if fig_desc:
                figure_data['description'] = fig_desc.get_text().strip()
            else:
                figure_data['description'] = ""
            
            # Extract graphic information if present
            graphic = figure.find('graphic')
            if graphic:
                figure_data['has_graphic'] = True
                figure_data['graphic_coords'] = graphic.get('coords', "")
                figure_data['graphic_type'] = graphic.get('type', "")
                
                # If this is a figure with only a graphic element and no other metadata,
                # try to create a figure number based on the coords attribute
                if not figure_data['figure_number'] and not figure_data['title'] and graphic.get('coords'):
                    coords = graphic.get('coords', "")
                    # The first number in coords is often the page number
                    parts = coords.split(',')
                    if parts and parts[0].strip().isdigit():
                        page_num = parts[0].strip()
                        figure_data['figure_number'] = f"Page {page_num}"
                        if not figure_data['title']:
                            figure_data['title'] = f"Graphic on Page {page_num}"
            else:
                figure_data['has_graphic'] = False
                figure_data['graphic_coords'] = ""
                figure_data['graphic_type'] = ""
            
            # Store the complete HTML of the figure for reference
            figure_data['html_content'] = str(figure)
            
            results.append(figure_data)
            
        except Exception as e:
            logger.error(f"Error processing figure {xml_id if 'xml_id' in locals() else 'unknown'}: {str(e)}")
    
    return results

def add_figures_to_supabase(figures: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Add extracted figures to Supabase
    
    Args:
        figures (list): List of figure data dictionaries
        
    Returns:
        dict: Result of the operation
    """
    if not figures:
        logger.warning("No figures to add to Supabase")
        return {"success": False, "message": "No figures to add", "count": 0}
    
    try:
        # Insert figures into Supabase
        response = supabase.table("GrobidFigureData").insert(figures).execute()
        
        return {
            "success": True,
            "message": f"Successfully added {len(figures)} figures to Supabase",
            "count": len(figures),
        }
    except Exception as e:
        error_details = str(e)
        logger.error(f"Error adding figures to Supabase: {error_details}")
        
        # Print complete error details for debugging
        print(f"Supabase error details: {error_details}")
        
        return {
            "success": False, 
            "message": f"Error: {error_details}", 
            "count": 0,
            "error": error_details
        }

def process_figures(tei_file_path: str, paper_summary_id: str) -> Dict[str, Any]:
    """
    Process and add figures from a TEI file to Supabase
    
    Args:
        tei_file_path (str): Path to the TEI XML file
        paper_summary_id (str): ID of the paper summary
        
    Returns:
        dict: Result of the operation
    """
    # Extract figures from the TEI file
    figures = extract_figures_from_tei(tei_file_path, paper_summary_id)
    
    if not figures:
        return {"success": False, "message": "No figures extracted", "count": 0}
    
    # Add figures to Supabase
    result = add_figures_to_supabase(figures)
    
    return result

# Example usage (if run directly)
if __name__ == "__main__":
    # For testing
    test_file = "./test_out/test.grobid.tei.xml"
    test_paper_id = "bc62dc9c-0e8c-4709-98ff-cc3678304295"
    
    if os.path.exists(test_file):
        result = process_figures(test_file, test_paper_id)
        print(json.dumps(result, indent=2))
    else:
        print(f"Test file {test_file} not found")