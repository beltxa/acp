FROM node:24-slim
WORKDIR /workspace

COPY sdks/typescript /workspace/sdks/typescript
COPY tools/poker-demo/typescript-player /workspace/tools/poker-demo/typescript-player

RUN cd /workspace/sdks/typescript && npm install && npm run build
RUN cd /workspace/tools/poker-demo/typescript-player && npm install && npm run build

WORKDIR /workspace/tools/poker-demo/typescript-player
EXPOSE 8091
ENTRYPOINT ["node", "dist/index.js"]
