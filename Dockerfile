FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN uv pip install --system --no-cache .

EXPOSE 8000

CMD ["uvicorn", "custos_examinis.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
