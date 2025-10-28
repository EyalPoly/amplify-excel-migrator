from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="amplify-excel-migrator",
    version="1.0.0",
    author="Eyal Politansky",
    author_email="10eyal10@gmail.com",
    description="A CLI tool to migrate Excel data to AWS Amplify",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/EyalPoly/amplify-excel-migrator",
    py_modules=["migrator", "amplify_client", "model_field_parser", "mapper"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pandas>=1.3.0",
        "requests>=2.26.0",
        "boto3>=1.18.0",
        "pycognito>=2023.5.0",
        "PyJWT>=2.0.0",
        "aiohttp>=3.8.0",
        "openpyxl>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "amplify-migrator=migrator:main",
        ],
    },
)