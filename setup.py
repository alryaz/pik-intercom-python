from typing import Final

import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

GITHUB_URL: Final = "https://github.com/alryaz/pik-intercom-python"

setuptools.setup(
    name="pik_intercom",
    author="Alexander Ryazanov",
    author_email="alryaz@alryaz.com",
    description="Example PyPI (Python Package Index) Package",
    keywords="example, pypi, package",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=GITHUB_URL,
    project_urls={
        "Documentation": GITHUB_URL,
        "Bug Reports": GITHUB_URL + "/issues",
        "Source Code": GITHUB_URL,
    },
    packages=setuptools.find_packages(exclude=["docs", "tests*"]),
    classifiers=[
        # see https://pypi.org/classifiers/
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
)
