FROM node:24-bookworm-slim

RUN mkdir /auth && chown node:node /auth
COPY gateway/gateway.mjs /app/gateway.mjs

USER node
CMD ["node", "/app/gateway.mjs"]
