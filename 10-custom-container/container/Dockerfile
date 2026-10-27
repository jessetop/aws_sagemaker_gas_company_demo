# A minimal "bring your own container" (BYOC) TRAINING image for SageMaker.
#
# SageMaker starts a training container by running:   docker run <image> train
# so the contract is simply: have an executable named `train` on the PATH.
# That's it — no framework, no toolkit. This is the clearest way to show students
# exactly what SageMaker expects of a container.

FROM python:3.11-slim

# Install just the ML dependencies. Pinned for reproducible demo builds.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Unbuffered stdout so training logs stream to your terminal / CloudWatch live.
ENV PYTHONUNBUFFERED=1

# The program SageMaker invokes. No file extension: the command is literally `train`.
COPY train /usr/local/bin/train
RUN chmod +x /usr/local/bin/train

# No ENTRYPOINT: `docker run <image> train` resolves `train` on PATH and runs it.
