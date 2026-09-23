FROM python:3.13-slim

WORKDIR /app

# git is optional — used only for local HEAD watch; ignore if missing
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway restartPolicy ALWAYS + in-process execv on /restart
CMD ["python", "zynex_cartel/main.py"]
