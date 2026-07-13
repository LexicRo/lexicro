FROM python:3.13-slim

WORKDIR /app

# CPU-only torch. The default wheel pulls CUDA and turns a 400MB image into 3GB.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY vendor/ ./vendor/

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]