FROM python:3.13-slim
WORKDIR /app
# opencv-python-headless needs a couple of shared libs even in headless mode.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sidecar.py .
ENTRYPOINT ["python", "sidecar.py"]
CMD ["--source", "demo", "--agent", "http://agent:9099"]
