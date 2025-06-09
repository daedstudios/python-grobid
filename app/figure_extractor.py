max_caption_distance = 200  # vertical proximity
max_caption_height = 200      # to avoid full paragraphs
max_heading_distance = 200
max_heading_height = 200

import pytesseract
import layoutparser as lp
from dotenv import load_dotenv
from supabase import create_client, Client
from pdf2image import convert_from_path
import os
import io
import uuid
from pathlib import Path
from PIL import Image as PILImage
import logging
import requests
from typing import Union, Tuple

# from app.utilities.uti import download_file


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

# Load the model
model = lp.Detectron2LayoutModel(
    config_path='lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config',
    label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.8]
)

def is_above(fig, txt):
    return txt.coordinates[3] <= fig.coordinates[1]

def is_below(fig, txt):
    return txt.coordinates[1] >= fig.coordinates[3]

def extract_and_upload_figures(paper_summary_id: str, bucket_name: str = "figure-images"):
    """
    Extract figures and tables from a PDF, upload them to Supabase storage,
    and add entries to the PaperFigures table.
    
    Args:
        paper_summary_id (str): UUID of the paper summary
        bucket_name (str): Supabase storage bucket name
        
    Returns:
        list: List of extracted figure/table data
    """
    logger.info(f"Processing paper with ID: {paper_summary_id}")
    
    # Get document info from Supabase
    response = supabase.table("PaperMainStructure").select("*").eq("id", str(paper_summary_id)).execute()
    if not response.data:
        logger.error(f"Error: No data found for id: {paper_summary_id}")
        return []
    
    data = response.data[0]
    pdf_url = data.get("pdf_file_path")
    
    if not pdf_url:
        logger.error("Error: PDF file path not found in the record")
        return []
    
    # Create directory based on document ID
    doc_dir = f"./documents/{str(paper_summary_id)}"
    file_name = os.path.basename(pdf_url)
    local_file_path = os.path.join(doc_dir, file_name)
    
    # Download the PDF file
    download_success, error_message = download_file(pdf_url, local_file_path, doc_dir)
    if not download_success:
        logger.error(f"Failed to download PDF: {error_message}")
        return []
    
    # Create output directory for temporary storage
    os.makedirs("output", exist_ok=True)
    
    # Convert PDF to images
    try:
        logger.info(f"Converting PDF to images: {local_file_path}")
        pages = convert_from_path(local_file_path, dpi=300)
        logger.info(f"Successfully converted {len(pages)} pages")
    except Exception as e:
        logger.error(f"Error converting PDF to images: {str(e)}")
        return []
    
    results = []
    
    for i, page in enumerate(pages):
        logger.info(f"Processing page {i+1}/{len(pages)}")
        layout = model.detect(page)
        
        figures = [b for b in layout if b.type == "Figure"]
        text_blocks = [b for b in layout if b.type == "Text"]
        table_blocks = [b for b in layout if b.type == "Table"]
        
        # Process figures
        for j, fig in enumerate(figures):
            try:
                # Extract the figure
                fig_img = page.crop(fig.coordinates)
                temp_path = f"output/page{i}_figure{j}.png"
                fig_img.save(temp_path)
                
                # Get heading text above
                heading_candidates = [
                    t for t in text_blocks
                    if is_above(fig, t)
                    and abs(fig.coordinates[1] - t.coordinates[3]) < max_heading_distance
                    and (t.coordinates[3] - t.coordinates[1]) < max_heading_height
                ]
                heading_candidates.sort(key=lambda t: abs(fig.coordinates[1] - t.coordinates[3]))
                
                heading_text = ""
                if heading_candidates:
                    heading_crop = page.crop(heading_candidates[0].coordinates)
                    heading_text = pytesseract.image_to_string(heading_crop)
                
                # Get caption text below
                caption_candidates = [
                    t for t in text_blocks
                    if is_below(fig, t)
                    and abs(t.coordinates[1] - fig.coordinates[3]) < max_caption_distance
                    and (t.coordinates[3] - t.coordinates[1]) < max_caption_height
                ]
                caption_candidates.sort(key=lambda t: abs(t.coordinates[1] - fig.coordinates[3]))
                
                caption_text = ""
                if caption_candidates:
                    caption_crop = page.crop(caption_candidates[0].coordinates)
                    caption_text = pytesseract.image_to_string(caption_crop)
                
                # Upload to Supabase
                figure_id = str(uuid.uuid4())
                storage_filename = f"{paper_summary_id}/{figure_id}.png"
                
                # Open the image and convert to bytes
                with open(temp_path, "rb") as img_file:
                    image_bytes = img_file.read()
                
                # Upload to Supabase storage
                supabase.storage.from_(bucket_name).upload(
                    path=storage_filename,
                    file=image_bytes,
                    file_options={"content-type": "image/png"}
                )
                
                # Get the public URL
                image_url = supabase.storage.from_(bucket_name).get_public_url(storage_filename)
                
                # Create entry in PaperFigures table
                figure_data = {
                    "paper_summary_id": paper_summary_id,
                    "figure_type": "figure",
                    "figure_id": f"fig-{i}-{j}",
                    "head": heading_text.strip(),
                    "description": caption_text.strip(),
                    # "coords": str(fig.coordinates.tolist()),
                    "extracted_image_path": temp_path,
                    "page_number": i + 1,
                    "source_file": local_file_path,
                    "image_url": image_url
                }
                
                # Insert into Supabase
                response = supabase.table("PaperFigures").insert(figure_data).execute()
                
                if response.data:
                    logger.info(f"Successfully added figure to database: {figure_id}")
                    figure_data["id"] = response.data[0]["id"]
                    results.append(figure_data)
                else:
                    logger.error("Failed to add figure to database")
                
            except Exception as e:
                logger.error(f"Error processing figure {j} on page {i}: {str(e)}")
        
        # Process tables
        for j, table in enumerate(table_blocks):
            try:
                # Extract the table
                table_img = page.crop(table.coordinates)
                temp_path = f"output/page{i}_table{j}.png"
                table_img.save(temp_path)
                
                # Get heading text above (similar to figures)
                heading_candidates = [
                    t for t in text_blocks
                    if is_above(table, t)
                    and abs(table.coordinates[1] - t.coordinates[3]) < max_heading_distance
                    and (t.coordinates[3] - t.coordinates[1]) < max_heading_height
                ]
                heading_candidates.sort(key=lambda t: abs(table.coordinates[1] - t.coordinates[3]))
                
                heading_text = ""
                if heading_candidates:
                    heading_crop = page.crop(heading_candidates[0].coordinates)
                    heading_text = pytesseract.image_to_string(heading_crop)
                
                # Get caption text below
                caption_candidates = [
                    t for t in text_blocks
                    if is_below(table, t)
                    and abs(t.coordinates[1] - table.coordinates[3]) < max_caption_distance
                    and (t.coordinates[3] - t.coordinates[1]) < max_caption_height
                ]
                caption_candidates.sort(key=lambda t: abs(t.coordinates[1] - table.coordinates[3]))
                
                caption_text = ""
                if caption_candidates:
                    caption_crop = page.crop(caption_candidates[0].coordinates)
                    caption_text = pytesseract.image_to_string(caption_crop)
                
                # Upload to Supabase
                table_id = str(uuid.uuid4())
                storage_filename = f"{paper_summary_id}/{table_id}.png"
                
                # Open the image and convert to bytes
                with open(temp_path, "rb") as img_file:
                    image_bytes = img_file.read()
                
                # Upload to Supabase storage
                supabase.storage.from_(bucket_name).upload(
                    path=storage_filename,
                    file=image_bytes,
                    file_options={"content-type": "image/png"}
                )
                
                # Get the public URL
                image_url = supabase.storage.from_(bucket_name).get_public_url(storage_filename)
                
                # Create entry in PaperFigures table
                table_data = {
                    "paper_summary_id": paper_summary_id,
                    "figure_type": "table",
                    "figure_id": f"table-{i}-{j}",
                    "head": heading_text.strip(),
                    "description": caption_text.strip(),
                    # "coords": str(table.coordinates.tolist()),
                    "extracted_image_path": temp_path,
                    "page_number": i + 1,
                    "source_file": local_file_path,
                    "image_url": image_url
                }
                
                # Insert into Supabase
                response = supabase.table("PaperFigures").insert(table_data).execute()
                
                if response.data:
                    logger.info(f"Successfully added table to database: {table_id}")
                    table_data["id"] = response.data[0]["id"]
                    results.append(table_data)
                else:
                    logger.error("Failed to add table to database")
                
            except Exception as e:
                logger.error(f"Error processing table {j} on page {i}: {str(e)}")
    
    logger.info(f"Finished processing paper {paper_summary_id}. Extracted {len(results)} figures/tables")
    return results

# Example usage
if __name__ == "__main__":
    # Replace with your actual paper_summary_id
    paper_id = "0303195f-486d-4089-8da3-d0e538ce1831"  # Example ID from your documents folder
    results = extract_and_upload_figures(paper_id)
    print(f"Extracted {len(results)} figures and tables")
