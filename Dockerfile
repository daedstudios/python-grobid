FROM frostpunk/layoutparser-detector

WORKDIR /code

COPY ./req.txt /code/requirements.txt

RUN pip install -r /code/requirements.txt

RUN pip install --force-reinstall --no-cache-dir pillow==9.5.0

RUN python -c "import layoutparser as lp; lp.Detectron2LayoutModel('lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config')"

EXPOSE 8000

COPY . /code/

CMD ["fastapi", "run", "main.py", "--port", "8000"]