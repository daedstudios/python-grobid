FROM python:3.12.3

WORKDIR /code

COPY ./req.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . /code/

EXPOSE 8000

CMD ["fastapi", "run", "main.py", "--port", "8000"]