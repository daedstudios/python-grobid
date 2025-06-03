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




def extract_divs_to_json(tei_file_path, paper_summary_id: str):
    """
    Extract divisions from TEI XML and store in Supabase
    
    Args:
        tei_file_path (str): Path to the TEI XML file
        paper_summary_id (str): ID of the paper summary
    """
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
            
            # Add paper and summary IDs
            div_obj['paperSummaryID'] = paper_summary_id
            result.append(div_obj)
    
    try:
        # Insert into Supabase
        content_response = (
            supabase.table("PaperContentGrobid")
            .insert(result)
            .execute()
        )
        return {
            "success": True,
            "message": f"Successfully inserted {len(result)} divisions",
            "data": content_response.data
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to insert data: {str(e)}",
            "data": None
        }
        
        