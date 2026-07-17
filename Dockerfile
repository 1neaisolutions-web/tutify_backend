# ============================================
# Tutify Backend - Dockerfile
# ============================================

# Step 1: Base image (lightweight Python)
FROM python:3.11-slim

# Step 2: System-level dependencies
# tesseract-ocr -> pytesseract ke liye
# poppler-utils -> pdf2image ke liye
# libpq-dev + gcc -> psycopg2-binary compile ke liye
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Step 3: Working directory set karo container ke andar
WORKDIR /app

# Step 4: Requirements pehle copy karo (layer caching ke liye)
COPY requirements.txt .

# Step 5: Python dependencies install karo
# --timeout aur --retries badhaye gaye hain slow/unstable internet connections handle karne ke liye
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r requirements.txt

# Step 6: Ab app code copy karo (yeh sabse zyada change hota hai, isliye sabse aakhir mein)
COPY . .

# Step 7: Port expose karo (sirf documentation purpose, actual mapping docker run mein hoti hai)
EXPOSE 8000

# Step 8: App start karne ka command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]