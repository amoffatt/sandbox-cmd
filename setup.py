#!/usr/bin/env python3
"""Setup script for Box - CLI container isolation tool"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text() if (this_directory / "README.md").exists() else ""

setup(
    name="box-cli",
    version="0.1.0",
    description="Create isolated CLI sessions within Docker or Podman containers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Aaron Moffatt",
    author_email="contact@aaronmoffatt.com",
    url="https://github.com/amoffatt/sandbox-cmd",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "box=box.cli:main",
            "box_sshfs=box.sshfs_cli:main",
        ],
    },
    python_requires=">=3.6",
    install_requires=[
    ],
    extras_require={
        'test': [
            'pytest>=7.0.0',
            'pytest-cov>=3.0.0',
            'pytest-mock>=3.6.0',
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    keywords="docker podman container cli isolation development",
)