FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package sources
COPY packages/core/ packages/core/
COPY packages/adapters/ packages/adapters/
COPY services/api/ services/api/

# Install packages
RUN pip install --no-cache-dir \
    packages/core/ \
    packages/adapters/ \
    services/api/

EXPOSE 8000

CMD ["uvicorn", "am_i_blocked_api:app", "--host", "0.0.0.0", "--port", "8000"]
