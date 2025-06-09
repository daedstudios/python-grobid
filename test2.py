import layoutparser as lp

from pdf2image import convert_from_path
import os

# Replace with your PDF path
pdf_path = "cell.pdf"
pages = convert_from_path(pdf_path, dpi=300)


os.makedirs("output2", exist_ok=True)

# Load the model (you already have this)
model = lp.Detectron2LayoutModel(
    config_path='lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config',
    label_map={0: "Text", 1: "Title", 2: "List", 3: "Table", 4: "Figure"},
    extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.8]
)

# Run detection on each page
for i, page in enumerate(pages):
    layout = model.detect(page)
    # Filter for Figure, List, and Table blocks
    figure_blocks = [b for b in layout if b.type == "Figure"]
    table_blocks = [b for b in layout if b.type == "Table"]

    # Save Figures
    for j, block in enumerate(figure_blocks):
        figure_image = page.crop(block.coordinates)
        figure_image.save(f"output2/page_{i}_figure_{j}.png")
    
    # Save Tables
    for j, block in enumerate(table_blocks):
        table_image = page.crop(block.coordinates)
        table_image.save(f"output2/page_{i}_table_{j}.png")