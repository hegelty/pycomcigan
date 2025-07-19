import os

import setuptools

# README.md 파일 존재 여부 확인
readme_path = "README.md"
if os.path.exists(readme_path):
    with open(readme_path, "r", encoding='UTF-8') as fh:
        long_description = fh.read()
else:
    long_description = "컴시간알리미 시간표 파싱 라이브러리입니다."

setuptools.setup(
    name="pycomcigan",
    version="1.3.0",
    author="hegelty",
    author_email="dev@hegelty.me",
    description="컴시간알리미 시간표 파싱 라이브러리입니다.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hegelty/pycomcigan",
    packages=setuptools.find_packages(),
    include_package_data=True,
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
    python_requires='>=3.9'
)
