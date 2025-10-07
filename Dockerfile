FROM python:3.11.3-slim

WORKDIR /app

RUN pip install --upgrade pip
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY ./main.py /app
COPY ./website /app/website

CMD python3 main.py