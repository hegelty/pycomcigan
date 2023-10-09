import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pycomcigan",
    version="1.0.3",
    author="hegelty",
    author_email="skxodid0305@gmail.com",
    description="컴시간알리미 시간표 파싱 라이브러리입니다.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hegelty/pycomcigan",
    packages=setuptools.find_packages(),
    install_requires=[
        'requests',
        'beautifulsoup4',
        'urllib3'
        ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent"
        ],
    python_requires='>=3.7'
)