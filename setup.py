import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pybls21",
    version="2.0.0",
    author="Julius Vitkauskas",
    author_email="zadintuvas@gmail.com",
    description="An api allowing control of AC state (temperature, on/off, speed) of an Blauberg S21 device locally over TCP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jvitkauskas/pybls21",
    packages=setuptools.find_packages(),
    install_requires=['pymodbus>=3.1.1,<4.0'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.4',
)
