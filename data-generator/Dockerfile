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

COPY generate.py sources.py schema.sql test_tables.py ./

# Fails the build if a weighted-choice table is malformed, rather than at
# runtime on whichever code path happens to reach it.
RUN python test_tables.py

# Seeds once, then serves: each tick appends a shaped amount of activity and
# sleeps for a jittered interval, so the demo has a pulse rather than a
# frozen snapshot. `serve` reseeds itself when the event table passes its
# cap or the seed reaches its max age.
CMD ["sh", "-c", "python generate.py seed \
  --customers ${DEMO_CUSTOMERS:-5000} \
  --orders ${DEMO_ORDERS:-60000} \
  --accounts ${DEMO_ACCOUNTS:-1200} \
  && exec python generate.py serve \
  --customers ${DEMO_CUSTOMERS:-5000} \
  --orders ${DEMO_ORDERS:-60000} \
  --accounts ${DEMO_ACCOUNTS:-1200} \
  --cap ${DEMO_ROW_CAP:-400000} \
  --max-age-days ${DEMO_MAX_AGE_DAYS:-30} \
  --tick-seconds ${DEMO_TICK_SECONDS:-300}"]
