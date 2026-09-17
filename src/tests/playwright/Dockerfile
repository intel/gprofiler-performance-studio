# Playwright UI test runner. Uses the official image (browsers + system deps
# preinstalled) so it works regardless of host libraries, and runs on the
# compose network to reach the console via the internal nginx service.
#
# Image tag MUST match the @playwright/test version in package.json.
FROM mcr.microsoft.com/playwright:v1.61.1-noble

WORKDIR /work
COPY package.json package-lock.json* ./
RUN npm install
COPY . .

CMD ["npx", "playwright", "test"]
