FROM python:3.11-slim

WORKDIR /app
COPY phase1/requirements.txt /app/phase1/requirements.txt
RUN pip install --no-cache-dir -r /app/phase1/requirements.txt

COPY phase1 /app/phase1
COPY phase2 /app/phase2

ENV HOST=0.0.0.0
ENV PORT=10000
ENV APP_MODE=demo

EXPOSE 10000
CMD ["python", "phase1/app.py"]
