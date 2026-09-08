FROM node:22-bookworm-slim
RUN mkdir /auth && chown node:node /auth
COPY gateway.mjs /app/gateway.mjs
USER node
CMD ["node", "/app/gateway.mjs"]
