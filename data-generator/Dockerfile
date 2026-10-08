# Seeds the synthetic dataset on boot, then keeps it moving.
#
# Two behaviours in one container, because they answer the same question at
# different times: `seed` makes the demo look real the first time anyone opens
# it, and `append` keeps its charts from looking frozen the rest of the time.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    DEMO_EXPORT_DIR=/out

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY generate.py schema.sql ./

# The seed is idempotent and takes a couple of minutes at full size, so it runs
# to completion before the first append rather than racing it.
CMD ["sh", "-c", "python generate.py seed && while true; do sleep 300 && python generate.py append --count 25 || true; done"]
