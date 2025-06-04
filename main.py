from grobid_client.grobid_client import GrobidClient

from typing import Union
from uuid import UUID
import uuid
import logging
from fastapi import FastAPI, HTTPException
from bs4 import BeautifulSoup
import json
import os
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
    
    # Create directory based on document ID
    doc_dir = f"./documents/{str(id)}"
    os.makedirs(doc_dir, exist_ok=True)
    
    file_name = os.path.basename(pdf_file_path)
    local_file_path = os.path.join(doc_dir, file_name)
    
    try:
        import requests
        response = requests.get(pdf_file_path)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        with open(local_file_path, "wb") as f:
            f.write(response.content)
        
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
        print(f"Error: Failed to download PDF: {str(e)}")
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

