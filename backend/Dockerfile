FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY chronomem ./chronomem
RUN uv pip install --system --no-cache .
ENV PORT=8000
EXPOSE 8000
CMD ["python", "-m", "chronomem.api"]
