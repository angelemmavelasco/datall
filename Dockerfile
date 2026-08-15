FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY package.json /app/
RUN npm install

COPY . /app/
RUN npm run build:css

EXPOSE 8000

CMD sh -c "python manage.py collectstatic --noinput && exec gunicorn config.asgi:application -k uvicorn.workers.UvicornWorker --workers 4 --bind 0.0.0.0:8000"