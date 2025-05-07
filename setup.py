#!/usr/bin/env python3
"""
Setup script for raspberry_pie_camera_capture package.
"""

from setuptools import setup, find_packages

setup(
    name="raspberry_pie_camera_capture",
    version="0.1.0",
    description="Camera capture and streaming for Raspberry Pi",
    author="Anzal",
    author_email="anzal.ks@gmail.com",
    url="https://github.com/anzalks/raspberry_pie_camera_capture",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "numpy",
        "opencv-python",
        "picamera2",
        "pylsl",
        "requests",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "camera-capture=raspberry_pi_lsl_stream.camera_capture:main",
            "test-camera=tests.test_camera_trigger:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Multimedia :: Video :: Capture",
    ],
) 