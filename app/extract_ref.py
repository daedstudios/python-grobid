from typing import Union
import uuid
import logging
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime
from typing import Dict, List, Optional, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('reference_extractor')

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def extract_biblstruct_to_json(tei_file_path: str, paper_summary_id: str) -> List[Dict[str, Any]]:
    """
    Extract bibliography references from TEI XML and convert to structured JSON format
    
    Args:
        tei_file_path (str): Path to the TEI XML file
        paper_summary_id (str): ID of the paper summary
        
    Returns:
        list: Extracted bibliography reference data
    """
    logger.info(f"Extracting references from {tei_file_path}")
    
    try:
        with open(tei_file_path, 'r', encoding='utf-8') as tei:
            soup = BeautifulSoup(tei, 'lxml-xml')
    except Exception as e:
        logger.error(f"Error opening or parsing TEI file: {str(e)}")
        return []
    
    biblstructs = soup.find_all('biblStruct')
    logger.info(f"Found {len(biblstructs)} references in the document")
    
    results = []
    
    for biblstruct in biblstructs:
        try:
            reference_data = {}
            
            # Extract the ID
            xml_id = biblstruct.get('xml:id', '')
            reference_data['xml_id'] = xml_id
            
            # Extract DOI and URL if present
            doi = None
            url = None
            
            idno_doi = biblstruct.find('idno', {'type': 'DOI'})
            if idno_doi:
                doi = idno_doi.text.strip()
            
            ptr = biblstruct.find('ptr')
            if ptr and ptr.get('target'):
                url = ptr.get('target')
            
            reference_data['doi'] = doi
            reference_data['url'] = url
            
            # Extract title information
            title_analytic = biblstruct.find('analytic', {})
            title_monogr = biblstruct.find('monogr', {})
            
            if title_analytic and title_analytic.find('title'):
                title_elem = title_analytic.find('title')
                reference_data['title'] = title_elem.text.strip()
                reference_data['title_level'] = title_elem.get('level', '')
                reference_data['title_type'] = title_elem.get('type', '')
            elif title_monogr and title_monogr.find('title'):
                title_elem = title_monogr.find('title')
                reference_data['title'] = title_elem.text.strip()
                reference_data['title_level'] = title_elem.get('level', '')
                reference_data['title_type'] = title_elem.get('type', '')
            else:
                reference_data['title'] = ''
                reference_data['title_level'] = ''
                reference_data['title_type'] = ''
            
            # Extract authors
            authors = []
            author_elements = []
            
            if title_analytic:
                author_elements = title_analytic.find_all('author')
            
            if not author_elements and title_monogr:
                author_elements = title_monogr.find_all('author')
            
            for author in author_elements:
                author_data = {}
                person_name = author.find('persName')
                
                if person_name:
                    forename = person_name.find('forename')
                    surname = person_name.find('surname')
                    
                    if forename:
                        author_data['forename'] = forename.text.strip()
                        author_data['forename_type'] = forename.get('type', '')
                    
                    if surname:
                        author_data['surname'] = surname.text.strip()
                
                if author_data:
                    authors.append(author_data)
            
            reference_data['authors'] = authors
            
            # Extract journal/book information
            if title_monogr:
                journal_title = title_monogr.find('title', {'level': 'j'})
                if journal_title:
                    reference_data['journal'] = journal_title.text.strip()
                
                imprint = title_monogr.find('imprint')
                if imprint:
                    # Extract volume, issue, pages
                    volume = imprint.find('biblScope', {'unit': 'volume'})
                    if volume:
                        reference_data['volume'] = volume.text.strip()
                    
                    issue = imprint.find('biblScope', {'unit': 'issue'})
                    if issue:
                        reference_data['issue'] = issue.text.strip()
                    
                    # Handle page ranges
                    page = imprint.find('biblScope', {'unit': 'page'})
                    if page:
                        reference_data['page_from'] = page.get('from', '')
                        reference_data['page_to'] = page.get('to', '')
                        
                        # If from/to attributes aren't present, use text content
                        if not reference_data['page_from'] and not reference_data['page_to']:
                            reference_data['page_range'] = page.text.strip()
                    
                    # Extract publication date
                    date = imprint.find('date')
                    if date:
                        reference_data['publication_date'] = date.get('when', '')
                        reference_data['date_type'] = date.get('type', '')
            
            # Add paper summary ID
            reference_data['paper_summary_id'] = paper_summary_id
            
            # Generate a unique ID for this reference
            reference_data['id'] = str(uuid.uuid4())
            
            # Add timestamp
            current_time = datetime.datetime.now().isoformat()
            reference_data['created_at'] = current_time
            reference_data['updated_at'] = current_time
            
            results.append(reference_data)
            
        except Exception as e:
            logger.error(f"Error processing reference {xml_id if 'xml_id' in locals() else 'unknown'}: {str(e)}")
    
    return results

def add_references_to_supabase(references: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Add extracted references to Supabase based on the Reference and ReferenceAuthor schema
    
    Args:
        references (list): List of reference data dictionaries
        
    Returns:
        dict: Result of the operation
    """
    if not references:
        logger.warning("No references to add to Supabase")
        return {"success": False, "message": "No references to add", "count": 0}
    
    try:
        # Track the number of successfully added references and authors
        added_references = 0
        added_authors = 0
        
        for reference_data in references:
            try:
                # First, create a copy of the reference_data without the authors
                reference_to_insert = reference_data.copy()
                authors_data = reference_to_insert.pop('authors')  # Remove authors from the data
                
                # Insert the reference without authors
                reference_response = supabase.table("Reference").insert(reference_to_insert).execute()
                
                # Check if the reference was inserted successfully
                if reference_response and reference_response.data:
                    added_references += 1
                    reference_id = reference_to_insert['id']  # Use the pre-generated ID
                    
                    # Now insert each author with the reference_id
                    for position, author in enumerate(authors_data):
                        author_data = {
                            'id': str(uuid.uuid4()),
                            'reference_id': reference_id,
                            'forename': author.get('forename', ''),
                            'forename_type': author.get('forename_type', ''),
                            'surname': author.get('surname', ''),
                            'position': position  # To maintain the original order
                        }
                        
                        # Insert the author
                        author_response = supabase.table("ReferenceAuthor").insert(author_data).execute()
                        if author_response and author_response.data:
                            added_authors += 1
                else:
                    logger.warning(f"Failed to insert reference with ID {reference_data.get('id')}")
            
            except Exception as e:
                logger.error(f"Error processing reference {reference_data.get('id')}: {str(e)}")
                # Continue with the next reference instead of failing entirely
                continue
        
        return {
            "success": added_references > 0,
            "message": f"Successfully added {added_references} references with {added_authors} authors",
            "count": added_references,
            "authors_count": added_authors
        }
    
    except Exception as e:
        error_details = str(e)
        logger.error(f"Error adding references to Supabase: {error_details}")
        
        # Print complete error details for debugging
        print(f"Supabase error details: {error_details}")
        
        return {
            "success": False, 
            "message": f"Error: {error_details}", 
            "count": 0,
            "error": error_details
        }



def process_references(tei_file_path: str, paper_summary_id: str) -> Dict[str, Any]:
    """
    Process and add references from a TEI file to Supabase
    
    Args:
        tei_file_path (str): Path to the TEI XML file
        paper_summary_id (str): ID of the paper summary
        
    Returns:
        dict: Result of the operation
    """
    # Extract references from the TEI file
    references = extract_biblstruct_to_json(tei_file_path, paper_summary_id)
    
    if not references:
        return {"success": False, "message": "No references extracted", "count": 0}
    
    # Add references to Supabase
    result = add_references_to_supabase(references)
    
    return result

# Example usage (if run directly)
if __name__ == "__main__":
    # For testing
    test_file = "./test_out/test.grobid.tei.xml"
    test_paper_id = "12345678-1234-5678-1234-567812345678"
    
    if os.path.exists(test_file):
        result = process_references(test_file, test_paper_id)
        print(json.dumps(result, indent=2))
    else:
        print(f"Test file {test_file} not found")