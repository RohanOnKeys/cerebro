FROM python:3.12-slim

WORKDIR /app

# Dependencies first for layer caching — pinned from poetry.lock via
# `poetry export`, so this stays a plain pip install with no need for the
# poetry CLI (and its plugin machinery) to exist inside the image at all.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000

CMD ["cerebro-webhook"]
