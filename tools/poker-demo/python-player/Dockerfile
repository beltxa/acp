FROM python:3.12-slim
WORKDIR /app

COPY sdks/python /workspace/sdks/python
COPY tools/poker-demo/python-player /app

RUN pip install --no-cache-dir /workspace/sdks/python

EXPOSE 8091
ENTRYPOINT ["python", "/app/app.py"]
