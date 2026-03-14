FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY acp-sdk-python ./acp-sdk-python
COPY tools/python-chess-player ./tools/python-chess-player

RUN pip install --no-cache-dir /workspace/acp-sdk-python
RUN pip install --no-cache-dir /workspace/tools/python-chess-player

WORKDIR /workspace/tools/python-chess-player

EXPOSE 8088

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${CHESS_AGENT_SERVER_PORT:-8088}"]
