FROM node:24-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo git curl ca-certificates ripgrep python3 python3-venv build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && echo 'node ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/node \
    && chmod 440 /etc/sudoers.d/node

RUN npm install -g @anthropic-ai/claude-code @openai/codex \
    && chown node:node /usr/local /usr/local/lib \
    && chown -R node:node /usr/local/lib/node_modules /usr/local/bin

USER node
ENV HOME=/home/node
WORKDIR /workspace
CMD ["sleep", "infinity"]
