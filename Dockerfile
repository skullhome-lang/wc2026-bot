FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# bot_state.json пишется в /app — смонтируй том, чтобы переживать перезапуски
CMD ["python", "bot.py"]
