FROM python:3.11.3-slim

RUN useradd -ms /bin/sh -u 1001 app
USER app

WORKDIR /app

RUN pip install --upgrade pip
COPY ./requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

COPY ./main.py /app
COPY ./website /app/website

COPY --chown=app:app . /app

RUN mkdir -p /app/import && chmod 777 /app/import

CMD python3 main.py