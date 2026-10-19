FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY financial_engine ./financial_engine
COPY backend ./backend
COPY exports ./exports
COPY ai ./ai
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
