# 
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

# Base image
FROM python:3.11-slim

# Set environment variables for Poetry and AWS
ENV POETRY_HOME="/opt/poetry" \
    PATH="/opt/poetry/bin:$PATH" \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1 \
    AWS_DEFAULT_REGION=eu-central-1

# Install system dependencies and Poetry
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libavcodec-extra \
    libmagic1 \
    pandoc \
    texlive-latex-base \
    curl \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    # Chrome dependencies for selenium
    chromium \
    chromium-driver \
    && curl -sSL https://install.python-poetry.org | POETRY_HOME=$POETRY_HOME python3 - --version 2.1.1 \
    && apt-get purge -y curl wget gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only dependency files first to leverage Docker cache
COPY pyproject.toml poetry.lock ./

# Install Python dependencies using Poetry
RUN poetry install --no-root --only main -vvv


# Copy application code
COPY . .

# Run the application
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]