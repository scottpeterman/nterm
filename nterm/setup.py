"""
nterm - A themeable SSH terminal widget for PyQt6.
"""

from setuptools import setup, find_packages
from pathlib import Path

readme = Path(__file__).parent / "README.md"
long_description = readme.read_text() if readme.exists() else ""

setup(
    name="nterm",
    version="0.1.0",
    author="Scott Peterman",
    description="A themeable SSH terminal widget for PyQt6 with jump host support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/scottpeterman/nterm",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "nterm.terminal": ["resources/*"],
        "nterm.theme": ["themes/*.yaml"],
    },
    python_requires=">=3.10",
    install_requires=[
        "PyQt6>=6.4.0",
        "PyQt6-WebEngine>=6.4.0",
        "paramiko>=3.0.0",
        "cryptography>=41.0.0",
        "PyYAML>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-qt>=4.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Networking",
        "Topic :: Terminals :: Terminal Emulators/X Terminals",
    ],
    keywords="ssh terminal pyqt6 xterm paramiko network",
)
