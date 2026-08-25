# Serves both phase1-api and phase1-worker in the merged compose stack (see
# docker-compose.yml) -- one image, the worker service just overrides the
# command. Playwright's bundled Chromium is installed at build time so PDF
# export (server.js's /api/exports/:id/pdf) works out of the box in the
# container without CHROME_PATH pointing at a host browser.
FROM node:22-bookworm-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev --no-audit --no-fund \
  && npx --yes playwright install --with-deps chromium

COPY . .

ENV NODE_ENV=production
EXPOSE 4180

CMD ["node", "server.js"]
