# ── Base Image ────────────────────────────────────────────────
# Start from official Python 3.11 slim image
# slim = smaller size than full image, has everything we need
FROM python:3.11-slim

# ── Environment Variables ─────────────────────────────────────
# Prevents Python from writing .pyc files to disk (cleaner container)
ENV PYTHONDONTWRITEBYTECODE=1

# Prevents Python from buffering stdout/stderr
# Means print() and logs appear immediately in docker logs
ENV PYTHONUNBUFFERED=1

# ── Working Directory ─────────────────────────────────────────
# All commands from here on run inside /app inside the container
# This is where your project code will live
WORKDIR /app

# ── System Dependencies ───────────────────────────────────────
# Install system-level packages needed before Python packages
# pkg-config and default-libmysqlclient-dev → needed for mysqlclient (MySQL connector)
# gcc → needed to compile some Python packages
# These are OS-level packages, not Python packages
RUN apt-get update \
    && apt-get install -y \
        pkg-config \
        default-libmysqlclient-dev \
        gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Python Dependencies ───────────────────────────────────────
# Copy requirements.txt FIRST (before copying all code)
# This is a Docker best practice — if your code changes but
# requirements.txt doesn't, Docker reuses the cached pip install layer
# This makes rebuilds much faster
COPY requirements.txt .

# Install all Python packages from requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# ── Project Code ──────────────────────────────────────────────
# Copy your entire project into /app inside the container
# The first . means "everything in your current directory on Mac"
# The second . means "put it in /app inside the container"
COPY . .

# ── Port ──────────────────────────────────────────────────────
# Tell Docker that this container listens on port 8000
# This doesn't publish the port — docker-compose handles that
EXPOSE 8000

# ── Start Command ─────────────────────────────────────────────
# Command that runs when the container starts
# 0.0.0.0 makes Django listen on all network interfaces
# (not just localhost) so it's reachable from outside the container
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]