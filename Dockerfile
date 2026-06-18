FROM python:3.12-slim

#avoid using files .pyc and write it in console
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . /app/

RUN tailwindcss -i static/src/input.css -o static/css/output.css --minify
EXPOSE 8000

CMD sh -c "python manage.py collectstatic --noinput && exec gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --workers 5 --bind 0.0.0.0:8000"