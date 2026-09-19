FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY server.py .

ENV MCP_TRANSPORT=http
EXPOSE 9000

CMD ["python", "server.py"]
