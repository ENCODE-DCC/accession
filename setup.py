import setuptools
from setuptools import setup


def readme():
    with open('README.md') as f:
        return f.read()

setup(name='accession',
      version='0.0.16',
      description='Accessioning tool to submit genomics pipeline outputs to the ENCODE Portal',
      long_description=readme(),
      long_description_content_type='text/markdown',
      url='http://github.com/ENCODE-DCC/accession',
      author='Ulugbek Baymuradov',
      author_email='ulugbekbk@gmail.com',
      license='MIT',
      packages=setuptools.find_packages(),
      install_requires=[
          'requests',
          'encode_utils==2.5.0',
          'google-cloud-storage'
      ],
      zip_safe=False,
      entry_points={
          'console_scripts': ['accession=accession.__main__:main'],
      },
      classifiers=[
          "Programming Language :: Python :: 3",
          "License :: OSI Approved :: MIT License",
          "Operating System :: OS Independent",
      ],
      include_package_data=True
      )