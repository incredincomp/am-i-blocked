FROM python:3.12-slim

WORKDIR /app

# Copy package sources
COPY packages/core/ packages/core/
COPY packages/adapters/ packages/adapters/
COPY services/worker/ services/worker/

# Install packages
RUN pip install --no-cache-dir \
    packages/core/ \
    packages/adapters/ \
    services/worker/

CMD ["python", "-m", "am_i_blocked_worker.main"]
