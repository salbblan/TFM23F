FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests beautifulsoup4 pandas tqdm python-dateutil spacy rapidfuzz networkx pyvis 

COPY . .

CMD ["bash"]