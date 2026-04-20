ARG BASE_IMAGE=nvcr.io/nvidia/isaac-sim:5.1.0
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG APP_DIR=/workspace/GlobalHumanoidRobotChallenge2026_Baseline
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV DEBIAN_FRONTEND=noninteractive \
    ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y \
    XDG_RUNTIME_DIR=/tmp \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=${APP_DIR}

USER root

RUN mkdir -p /var/lib/apt/lists/partial \
    && apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . ${APP_DIR}

# Install dependencies into Isaac Sim's Python environment.
RUN /isaac-sim/python.sh -m pip install --no-cache-dir -i ${PIP_INDEX_URL} \
    "cmake>=3.29.0.1" \
    "datasets>=2.19.0" \
    "deepdiff>=7.0.1" \
    "diffusers>=0.27.2" \
    "draccus>=0.10.0" \
    "einops>=0.8.0" \
    "flask>=3.0.3" \
    "gdown>=5.1.0" \
    "gymnasium==0.29.1" \
    "h5py>=3.10.0" \
    "huggingface-hub>=0.27.1" \
    "imageio[ffmpeg]>=2.34.0" \
    "jsonlines>=4.0.0" \
    "numba>=0.59.0" \
    "omegaconf>=2.3.0" \
    "opencv-python>=4.9.0" \
    "packaging==23.0" \
    "av>=12.0.5,<13.0.0" \
    "pymunk>=6.6.0" \
    "pyzmq>=26.2.1" \
    "termcolor>=2.4.0" \
    "wandb>=0.16.3" \
    "zarr>=2.17.0" \
    "safetensors" \
    "regex" \
    "python-xlib" \
    "pin" \
    "numpy<1.27,>=1.22" \
    "transformers>=4.48.0" \
    "pytest>=8.1.0" \
    && /isaac-sim/python.sh -m pip install --no-cache-dir -i ${PIP_INDEX_URL} --no-deps \
    "pynput>=1.7.7" \
    && /isaac-sim/python.sh -m pip install --no-cache-dir --no-deps -e ${APP_DIR}

WORKDIR ${APP_DIR}

CMD ["/bin/bash"]
