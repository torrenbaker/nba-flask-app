# Use the official Python image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy project files into the container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Command to run the Flask app
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:$PORT", "nba_backend:app"]
