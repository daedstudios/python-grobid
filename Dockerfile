FROM frostpunk/layoutparser-detector

WORKDIR /app

COPY ./req.txt /app/requirements.txt

RUN pip install -r /app/requirements.txt

RUN pip install --force-reinstall --no-cache-dir pillow==9.5.0

RUN python -c "import layoutparser as lp; lp.Detectron2LayoutModel('lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config')"

EXPOSE 8000

COPY . /app/

CMD ["fastapi", "run", "main.py", "--port", "8000"]