# Use official Python 3.12 slim image
FROM python:3.12.7-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files into the container
COPY . .

# Expose the OCPP server port
EXPOSE 9000

# Create logs folder
RUN mkdir -p logs

# Set environment variable for UTF-8 output
ENV PYTHONUNBUFFERED=1

# Command to run the server
CMD ["python", "server.py"]
