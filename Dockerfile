# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
# We use uv to generate requirements.txt first or just install directly.
# Since we used uv init, we have pyproject.toml.
# We'll install uv in the container and use it to sync.
RUN pip install uv

# Sync dependencies
RUN uv sync

# Make port 80 available to the world outside this container (optional, not needed for polling bot)
# EXPOSE 80

# Run the application as a module so package imports resolve
CMD ["uv", "run", "python", "-m", "app.main"]
