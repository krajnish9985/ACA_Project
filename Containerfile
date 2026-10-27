FROM docker.io/library/ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    gcc-7 \
    g++-7 \
    build-essential \
    git \
    cmake \
    python3 \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Make GCC 7 and G++ 7 the default compilers
RUN update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-7 70 && \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-7 70 && \
    update-alternatives --set gcc /usr/bin/gcc-7 && \
    update-alternatives --set g++ /usr/bin/g++-7


ENV CC=gcc-7
ENV CXX=g++-7
ENV PIN_ROOT=/workspace/pin

WORKDIR /workspace

