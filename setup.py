#!/usr/bin/env python3

from setuptools import setup, find_packages
import os

# Set a default version if _version.py is not found
__version__ = "0.1.0"

# Try to read version from _version.py
try:
    with open('src/raspberry_pi_lsl_stream/_version.py', 'r') as f:
        exec(f.read())  # This will define __version__
except (FileNotFoundError, IOError):
    # If file is not found, use default version
    pass

setup(
    name="raspie-capture",
    version=__version__,
    description="Capture video and audio from Raspberry Pi with LSL streaming",
    author="Anzal",
    author_email="anzal.ks@gmail.com",
    url="https://github.com/anzalks/raspberry_pie_camera_capture",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.7",
    install_requires=[
        "numpy",
        "opencv-python",
        "pylsl",
        "requests",
        "scipy",
        "sounddevice",
    ],
    entry_points={
        "console_scripts": [
            "rpi-lsl-stream=raspberry_pi_lsl_stream.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
) 