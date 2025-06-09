from grobid_client.grobid_client import GrobidClient

from typing import Union, Tuple
from uuid import UUID
import uuid
import logging
from fastapi import FastAPI, HTTPException
from bs4 import BeautifulSoup
import json
import os
import requests
from dotenv import load_dotenv
from supabase import create_client, Client
import datetime  

import fitz  # PyMuPDF
# import cv2
import numpy as np
from PIL import Image
from .app.extract import extract_divs_to_json
from fastapi.middleware.cors import CORSMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('grobid_processor')

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

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

def process_grobid(id: UUID):
    if not id:
        logger.error("Error: ID is required")
        return None
    
    response = supabase.table("PaperMainStructure").select("*").eq("id", str(id)).execute()
    
    if not response.data:
        logger.error(f"Error: No data found for id: {id}")
        return None
    
    data = response.data[0]
    pdf_file_path = data.get("pdf_file_path")
    
    if not pdf_file_path:
        logger.error("Error: PDF file path not found in the record")
        return None
    
    # Create directory based on document ID
    doc_dir = f"./documents/{str(id)}"
    
    file_name = os.path.basename(pdf_file_path)
    local_file_path = os.path.join(doc_dir, file_name)
    
    try:
        # Download the PDF file
        download_success, error_message = download_file(pdf_file_path, local_file_path, doc_dir)
        if not download_success:
            logger.error(f"Failed to download PDF: {error_message}")
            return None
        
        client = GrobidClient(config_path="./config.json", check_server=False)
        client.process("processFulltextDocument", doc_dir, output=f"{doc_dir}/", force=True, verbose=True)
        
        # Process the TEI output
        tei_file_path = local_file_path.replace('.pdf', '.grobid.tei.xml')
        if os.path.exists(tei_file_path):
            logger.info(f"Processing TEI file: {tei_file_path}")
            extract_result = extract_divs_to_json(
                tei_file_path=tei_file_path,
                paper_summary_id=str(id)
            )
            
            if not extract_result['success']:
                logger.error(f"Failed to process TEI: {extract_result['message']}")
                return None
            
            return {
                "message": "PDF processed and data extracted successfully",
                "data": data,
                "local_file_path": local_file_path,
                "extraction_result": extract_result
            }
        else:
            logger.error(f"TEI file not found: {tei_file_path}")
            return None
    
    except Exception as e:
        logger.error(f"Error: Failed to process PDF: {str(e)}")
        return None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

@app.get("/process/{id}")
async def process_document(id: str):
    try:
        document_id = UUID(id)
        result = process_grobid(document_id)
        if result:
            return result
        else:
            raise HTTPException(status_code=404, detail="Processing failed")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

