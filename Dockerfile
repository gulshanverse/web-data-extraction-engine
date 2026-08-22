FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml README.md LICENSE ./
COPY services/api/src ./services/api/src
RUN pip install --no-cache-dir -e .

COPY . .
CMD ["uvicorn", "wde_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
