#!/usr/bin/env python3
"""
Setup script for raspberry_pie_camera_capture package.
"""

from setuptools import setup, find_packages

setup(
    name="raspberry_pi_lsl_stream",
    version="0.1.0",
    description="Camera and Audio Capture for Raspberry Pi with LSL integration",
    author="Anzal",
    author_email="anzal.ks@gmail.com",
    url="https://github.com/anzalks/raspberry_pie_camera_capture",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.7",
    install_requires=[
        "pylsl",
        "numpy",
        "opencv-python",
        "requests",
        "psutil",
        # Audio requirements, will be installed if available
        "sounddevice;platform_system!='Windows' or platform_python_implementation!='PyPy'",
        "scipy",
    ],
    extras_require={
        "dev": [
            "pytest",
            "flake8",
            "black",
            "isort",
        ],
        "pi": [
            "picamera2",
        ],
    },
    entry_points={
        "console_scripts": [
            "camera-capture=raspberry_pi_lsl_stream.camera_capture:main",
            "audio-stream=raspberry_pi_lsl_stream.audio_stream:main",
            "test-camera=raspberry_pi_lsl_stream.test_camera:main",
            "check-camera-env=check_camera_env:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Scientific/Engineering",
    ],
) 