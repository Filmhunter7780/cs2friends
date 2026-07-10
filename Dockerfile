FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cs2_watch_bot.py .

CMD ["python", "cs2_watch_bot.py"]
