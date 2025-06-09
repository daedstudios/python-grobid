max_caption_distance = 200  # vertical proximity
max_caption_height = 200      # to avoid full paragraphs
max_heading_distance =200
max_heading_height = 200

import pytesseract

import layoutparser as lp

from pdf2image import convert_from_path
import os

# Replace with your PDF path
pdf_path = "test.pdf"
pages = convert_from_path(pdf_path, dpi=300)


os.makedirs("output", exist_ok=True)

# Load the model (you already have this)
model = lp.Detectron2LayoutModel(
    config_path='lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config',
    label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.8]
)

def is_above(fig, txt):
    return txt.coordinates[3] <= fig.coordinates[1]

def is_below(fig, txt):
    return txt.coordinates[1] >= fig.coordinates[3]

results = []

for i, page in enumerate(pages):
    layout = model.detect(page)
    figures = [b for b in layout if b.type == "Figure"]
    text_blocks = [b for b in layout if b.type == "Text"]

    for j, fig in enumerate(figures):
        fig_img = page.crop(fig.coordinates)
        fig_img.save(f"output/page{i}_figure{j}.png")

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

        results.append({
            "page": i,
            "figure_index": j,
            "image_file": f"output/page{i}_figure{j}.png",
            "heading": heading_text.strip(),
            "caption": caption_text.strip()
        })
        print({
            "page": i,
            "figure_index": j,
            "image_file": f"output/page{i}_figure{j}.png",
            "heading": heading_text.strip(),
            "caption": caption_text.strip()
        })
