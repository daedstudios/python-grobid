from typing import Union
import uuid

from fastapi import FastAPI

from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime  

import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image
from .utilities.uti import clean_text

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)


app = FastAPI()

tei_file_path = './test_pdf/cell.grobid.tei.xml'
pdf_path = './test_pdf/cell.pdf'



def extract_divs_to_json(tei_file_path):
    with open(tei_file_path, 'r', encoding='utf-8') as tei:
        soup = BeautifulSoup(tei, 'lxml-xml')
    
    body_content = soup.body
    result = []
    
    if body_content:
        divs = body_content.find_all('div', recursive=False)
        
        # Track the order of divisions in the XML
        order_index = 0
        
        for div in divs:
            div_obj = {}
            
            # Add order index to track position in the original XML
            div_obj['order_index'] = order_index
            order_index += 1
            
            # Extract the heading
            head = div.find('head')
            if head:
                # Get text content and clean up whitespace
                head_text = head.get_text()
                clean_head_text = ' '.join(head_text.split())
                div_obj['head'] = clean_head_text
                
                # Handle head_n which could be number or string
                head_n = head.get('n')
                if head_n:
                    # Store head_n as string regardless of content
                    div_obj['head_n'] = head_n.strip()
            else:
                div_obj['head'] = None
            
            # Extract paragraphs
            paras = div.find_all('p')
            div_obj['para'] = []
            
            # Track paragraph order within each div
            para_index = 0
            
            for p in paras:
                # Extract references in paragraph
                refs = p.find_all('ref')
                ref_markers = {}
                
                # Create mapping of reference positions
                for ref in refs:
                    ref_id = ref.get('coords', '')
                    ref_type = ref.get('type', '')
                    ref_text = ref.text
                    
                    # Store reference information with its text as identifier
                    ref_markers[ref_text] = {
                        'id': ref_id,
                        'type': ref_type
                    }
                
                # Add paragraph text with reference information
                # Clean up whitespace: normalize spaces and remove excessive whitespace
                text = p.get_text()
                clean_text = ' '.join(text.split())
                
                para_obj = {
                    'text': clean_text,
                    'refs': ref_markers,
                    'order_index': para_index
                }
                para_index += 1
                
                div_obj['para'].append(para_obj)
            
            result.append(div_obj)
    
    return result
        
        

def extract_metadata_from_tei(tei_file_path):
    """Extract metadata from a TEI XML file including title, authors, publication date, and abstract."""
    with open(tei_file_path, 'r', encoding='utf-8') as tei:
        soup = BeautifulSoup(tei, 'lxml-xml')
    
    metadata = {}
    
    # Extract title
    title_elem = soup.find('title', attrs={"type": "main"})
    if title_elem:
        metadata['title'] = clean_text(title_elem.get_text())
    
    # Extract authors
    authors = []
    author_elems = soup.find_all('author')
    for author_elem in author_elems:
        person_name = author_elem.find('persName')
        if person_name:
            forename = person_name.find('forename')
            surname = person_name.find('surname')
            if forename and surname:
                author = {
                    'forename': clean_text(forename.get_text()),
                    'surname': clean_text(surname.get_text())
                }
                
                # Extract affiliations
                affiliations = []
                affiliation_elems = author_elem.find_all('affiliation')
                for aff in affiliation_elems:
                    aff_data = {}
                    
                    # Get department if available
                    dept = aff.find('orgName', attrs={"type": "department"})
                    if dept:
                        aff_data['department'] = clean_text(dept.get_text())
                    
                    # Get institution
                    inst = aff.find('orgName', attrs={"type": "institution"})
                    if inst:
                        aff_data['institution'] = clean_text(inst.get_text())
                    
                    # Get country
                    country = aff.find('country')
                    if country:
                        aff_data['country'] = clean_text(country.get_text())
                        aff_data['country_code'] = country.get('key', '')
                    
                    if aff_data:
                        affiliations.append(aff_data)
                
                if affiliations:
                    author['affiliations'] = affiliations
                
                authors.append(author)
    
    if authors:
        metadata['authors'] = authors
    
    # Extract publication date
    pub_date = soup.find('date', attrs={"type": "published"})
    if pub_date:
        date_text = clean_text(pub_date.get_text())
        date_attr = pub_date.get('when')
        metadata['publication_date'] = {
            'text': date_text,
            'iso': date_attr if date_attr else date_text
        }
    
    # Extract abstract
    abstract_elem = soup.find('abstract')
    if abstract_elem:
        p_elem = abstract_elem.find('p')
        if p_elem:
            metadata['abstract'] = clean_text(p_elem.get_text())
    
    # Extract identifiers
    identifiers = {}
    id_elems = soup.find_all('idno')
    for id_elem in id_elems:
        id_type = id_elem.get('type')
        if id_type:
            identifiers[id_type] = clean_text(id_elem.get_text())
    
    if identifiers:
        metadata['identifiers'] = identifiers
    
    return metadata


def extract_images_from_page(pdf_path, page_number, supabase_client, bucket_name="images"):
    """
    Extract all images from a specific page in a PDF file and upload to Supabase
    
    Args:
        pdf_path: Path to the PDF file
        page_number: Page number to extract images from (0-based index)
        supabase_client: Initialized Supabase client
        bucket_name: Supabase storage bucket name
    
    Returns:
        List of dictionaries with image data including URLs
    """
    # Open the PDF
    pdf_document = fitz.open(pdf_path)
    
    # Check if page number is valid
    if page_number >= len(pdf_document) or page_number < 0:
        print(f"Invalid page number. PDF has {len(pdf_document)} pages.")
        return []
    
    # Get the specified page
    page = pdf_document[page_number]
    
    # Extract images
    image_list = page.get_images(full=True)
    extracted_images = []
    
    # Get filename for reference
    pdf_filename = os.path.basename(pdf_path)
    
    # Process each image
    for img_index, img in enumerate(image_list):
        try:
            xref = img[0]  # image reference
            base_image = pdf_document.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Generate unique filename for storage
            unique_id = str(uuid.uuid4())[:8]
            storage_filename = f"{pdf_filename.split('.')[0]}_page{page_number+1}_img{img_index}_{unique_id}.{image_ext}"
            
            # Upload directly to Supabase Storage
            supabase_client.storage.from_(bucket_name).upload(
                path=storage_filename,
                file=image_bytes,
                file_options={"content-type": f"image/{image_ext}"}
            )
            
            # Get the public URL for the uploaded image
            image_url = supabase_client.storage.from_(bucket_name).get_public_url(storage_filename)
            
            # Create image metadata
            image_info = {
                "page_number": page_number + 1,  # Convert to 1-based indexing
                "image_url": image_url,
                "filename": storage_filename,
                "width": base_image.get("width", 0),
                "height": base_image.get("height", 0),
                "image_ext": image_ext
            }
            
            extracted_images.append(image_info)
            print(f"Uploaded: {storage_filename} to Supabase Storage")
            
        except Exception as e:
            print(f"Error processing image {img_index} on page {page_number}: {str(e)}")
    
    # Close the document
    pdf_document.close()
    
    print(f"cvascva{extracted_images}")
    return extracted_images

def extract_figures_from_tei(tei_file_path):
    """Extract all figure data from a TEI XML file using BeautifulSoup."""
    
    with open(tei_file_path, 'r', encoding='utf-8') as tei:
        soup = BeautifulSoup(tei, 'lxml-xml')
    
    # Find all figure elements
    figures = soup.find_all('figure')
    
    # Lists to store different figure types
    bitmap_figures = []
    table_figures = []
    
    for fig in figures:
        # Basic figure data
        figure_data = {
            'id': fig.get('xml:id', ''),
            'type': fig.get('type', 'figure'),
            'coords': fig.get('coords', '')
        }
        
        # Extract head (caption)
        head = fig.find('head')
        figure_data['head'] = head.text.strip() if head else ''
        
        # Extract label (figure number)
        label = fig.find('label')
        figure_data['label'] = label.text.strip() if label else ''
        
        # Extract figure description
        fig_desc = fig.find('figDesc')
        figure_data['description'] = fig_desc.text.strip() if fig_desc else ''
        
        # Check for graphic element
        graphic = fig.find('graphic')
        if graphic:
            figure_data['graphic_type'] = graphic.get('type', '')
            figure_data['graphic_coords'] = graphic.get('coords', '')
        
        # Categorize figure based on its type
        if figure_data['type'] == 'table':
            table_figures.append(figure_data)
        elif graphic and graphic.get('type') == 'bitmap':
            bitmap_figures.append(figure_data)
        else:
            bitmap_figures.append(figure_data)  # Default to bitmap if not specified
    
    return {
        'bitmap_figures': bitmap_figures,
        'table_figures': table_figures
    }

        
@app.get("/process_paper")
def process_paper():
    try:
        # First extract metadata and create PaperSummary
        metadata = extract_metadata_from_tei(tei_file_path)
        
        filename = os.path.basename(tei_file_path)
        metadata['source_file'] = filename
        
        authors_list = [f"{author.get('forename', '')} {author.get('surname', '')}".strip() 
                        for author in metadata.get('authors', [])[:5]]
        
        if len(metadata.get('authors', [])) > 5:
            authors_list.append("et al.")
        
        current_timestamp = datetime.datetime.now().isoformat()
        
        paper_summary = {
            "title": metadata.get('title', ''),
            "fileName": filename,
            "url": metadata.get('identifiers', {}).get('DOI', metadata.get('identifiers', {}).get('arXiv', '')),
            "authors": authors_list,
            "publishedDate": metadata.get('publication_date', {}).get('iso', ''),
            "summary": metadata.get('abstract', ''),
            "updatedAt": current_timestamp,
            "createdAt": current_timestamp
        }
        
        # Insert the paper summary
        summary_response = (
            supabase.table("PaperSummary")
            .insert(paper_summary)
            .execute()
        )
        
        # Get the paper summary ID
        paper_summary_id = None
        if summary_response.data and len(summary_response.data) > 0:
            paper_summary_id = summary_response.data[0].get('id')
        
        # Now extract content and link it to the paper summary
        divs_json = extract_divs_to_json(tei_file_path)
        
        for div in divs_json:
            div['paper_id'] = filename
            div['paperSummaryID'] = paper_summary_id
        
        # Insert the content
        content_response = (
            supabase.table("PaperContentGrobid")
            .insert(divs_json)
            .execute()
        )
        
          # Extract figures from the TEI file
        figures_data = extract_figures_from_tei(tei_file_path)
        
        page_images = {}
        pdf_path = tei_file_path.replace('.grobid.tei.xml', '.pdf')
        
        # Collect all unique page numbers from the figures
        unique_pages = set()
        
        for fig in figures_data['bitmap_figures']:
            if fig.get('coords'):
                try:
                    page_number = int(fig['coords'].split(',')[0])
                    unique_pages.add(page_number)
                except (ValueError, IndexError):
                    pass
            elif fig.get('graphic_coords'):
                try:
                    page_number = int(fig['graphic_coords'].split(',')[0])
                    unique_pages.add(page_number)
                except (ValueError, IndexError):
                    pass
                    
        for table in figures_data['table_figures']:
            if table.get('coords'):
                try:
                    page_number = int(table['coords'].split(',')[0])
                    unique_pages.add(page_number)
                except (ValueError, IndexError):
                    pass
        
        # Extract images from each page that has figures
        for page_number in unique_pages:
            # Convert from 1-indexed to 0-indexed for the extraction function
            zero_indexed_page = page_number - 1
            
            # Extract and upload images from this page
            page_images[page_number] = extract_images_from_page(
                pdf_path=pdf_path, 
                page_number=zero_indexed_page,
                supabase_client=supabase,
                bucket_name="images"
            )
            
        # Prepare figures for insertion
        figures_to_insert = []
        
        print(f"Figures data: {page_images}")
        
        # Process bitmap figures
        for fig in figures_data['bitmap_figures']:
            # Extract page number from coordinates if available
            page_number = None
            image_url = None            
            if fig.get('coords'):
                try:
                    page_number = int(fig['coords'].split(',')[0])
                    
                    # Try to find a matching image for this figure
                    if page_number in page_images and page_images[page_number]:
                        # Just take the first image found on this page
                        # You might want to implement better matching logic
                        image_url = page_images[page_number][0]['image_url'] if page_images[page_number] else None
                except (ValueError, IndexError):
                    pass
            elif fig.get('graphic_coords'):
                try:
                    page_number = int(fig['graphic_coords'].split(',')[0])
                    
                    # Try to find a matching image for this figure
                    if page_number in page_images and page_images[page_number]:
                        # Just take the first image found on this page
                        image_url = page_images[page_number][0]['image_url'] if page_images[page_number] else None
                except (ValueError, IndexError):
                    pass
            
            figures_to_insert.append({
                "paper_summary_id": paper_summary_id,
                "figure_type": "figure",
                "figure_id": fig.get('id', ''),
                "label": fig.get('label', ''),
                "head": fig.get('head', ''),
                "description": fig.get('description', ''),
                "coords": fig.get('coords', ''),
                "graphic_type": fig.get('graphic_type', ''),
                "graphic_coords": fig.get('graphic_coords', ''),
                "page_number": page_number,
                "source_file": filename,
                "image_url": page_images[page_number]  # Add the image URL if found
            })
        
        # Process table figures
        for table in figures_data['table_figures']:
            # Extract page number from coordinates if available
            page_number = None
            image_url = None
            
            if table.get('coords'):
                try:
                    page_number = int(table['coords'].split(',')[0])
                    
                    # Try to find a matching image for this table
                    if page_number in page_images and page_images[page_number]:
                        # For tables, we might take the second image if available (tables often come after figures)
                        index_to_use = min(1, len(page_images[page_number])-1) if page_images[page_number] else 0
                        image_url = page_images[page_number][index_to_use]['image_url'] if page_images[page_number] else None
                except (ValueError, IndexError):
                    pass
            
            figures_to_insert.append({
                "paper_summary_id": paper_summary_id,
                "figure_type": "table",
                "figure_id": table.get('id', ''),
                "label": table.get('label', ''),
                "head": table.get('head', ''),
                "description": table.get('description', ''),
                "coords": table.get('coords', ''),
                "page_number": page_number,
                "source_file": filename,
                "image_url": image_url  # Add the image URL if found
            })
        
        # Insert figures into the database if we have any
        figures_response = None
        if figures_to_insert:
            figures_response = (
                supabase.table("PaperFigures")
                .insert(figures_to_insert)
                .execute()
            )
        
        # Count how many figures have images
        figures_with_images = sum(1 for fig in figures_to_insert if fig.get('image_url'))
        
        return {
            "success": True,
            "paper_summary_id": paper_summary_id,
            "metadata": metadata,
            "content_count": len(divs_json),
            "bitmap_figures_count": len(figures_data['bitmap_figures']),
            "table_figures_count": len(figures_data['table_figures']),
            "total_figures_count": len(figures_to_insert),
            "figures_with_images": figures_with_images
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }