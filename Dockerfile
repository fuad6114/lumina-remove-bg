# Python image ব্যবহার করছি
FROM python:3.9-slim

# কাজের ডিরেক্টরি সেট করা
WORKDIR /app

# সিস্টেম লাইব্রেরি ইনস্টল করার জন্য নতুন ও শক্তিশালী কমান্ড
RUN apt-get update && \
    apt-get install -y --no-install-recommends libglib2.0-0 libgl1-mesa-glx && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# পাইথন প্যাকেজ ইনস্টল করা
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# কোড কপি করা
COPY . .

# পোর্ট এক্সপোজ করা
EXPOSE 8000

# অ্যাপ রান করা
CMD ["python", "main.py"]