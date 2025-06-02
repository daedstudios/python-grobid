from grobid_client.grobid_client import GrobidClient

from typing import Union
from uuid import UUID
import uuid
import argparse
import sys
import logging

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

def process_grobid(id: UUID):
    if not id:
        print("Error: ID is required")
        return
    
    response = supabase.table("PaperMainStructure").select("*").eq("id", str(id)).execute()
    
    if not response.data:
        print(f"Error: No data found for id: {id}")
        return None
    
    data = response.data[0]
    pdf_file_path = data.get("pdf_file_path")
    
    if not pdf_file_path:
        print("Error: PDF file path not found in the record")
        return None
    
    os.makedirs("./test_pdf", exist_ok=True)
    
    file_name = os.path.basename(pdf_file_path)
    local_file_path = os.path.join("./test_pdf", file_name)
    
    try:
        import requests
        response = requests.get(pdf_file_path)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        with open(local_file_path, "wb") as f:
            f.write(response.content)
        
        client = GrobidClient(config_path="./config.json", check_server=False)
        client.process("processFulltextDocument", "./test_pdf", output="./test_pdf/", 
                      consolidate_citations=True, tei_coordinates=True, force=True, n=20)
        
        return {
            "message": "PDF downloaded successfully",
            "data": data,
            "local_file_path": local_file_path
        }
    
    except Exception as e:
        print(f"Error: Failed to download PDF: {str(e)}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process PDF files with GROBID')
    parser.add_argument('id', type=str, help='UUID of the document to process')
    
    args = parser.parse_args()
    
    try:
        document_id = UUID(args.id)
        result = process_grobid(document_id)
        if result:
            print(json.dumps(result, default=str, indent=2))
    except ValueError:
        print("Error: Invalid UUID format")
        sys.exit(1)
        
    
        