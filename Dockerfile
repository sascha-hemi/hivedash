FROM node:22-slim AS frontend-build

WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
# node:22-slim's bundled npm is older than the one the lockfile was generated with; a version
# mismatch here makes `npm ci` reject an otherwise-valid lockfile as "out of sync".
RUN npm install -g npm@11 && npm ci
COPY frontend/ ./
RUN npm run build -- --configuration production


FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
COPY --from=frontend-build /src/dist/frontend/browser ./app/static

EXPOSE 8000

# The DB lives on a mounted volume (see docker-compose.yml) - migrations run on every start so a
# schema change never needs a manual step, and are a no-op when already up to date.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
