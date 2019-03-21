from setuptools import setup

setup(name='accession',
      version='0.0.2',
      description='Accessioning tool to submit genomics pipeline outputs to the ENCODE Portal',
      url='http://github.com/ENCODE-DCC/accession',
      author='Ulugbek Baymuradov',
      author_email='ulugbekbk@gmail.com',
      license='MIT',
      packages=['funniest'],
      install_requires=[
          'requests',
          'encode_utils==2.5.0',
          'google-cloud-storage'
      ],
      zip_safe=False,
      entry_points={
          'console_scripts': ['accession=accession.__main__:main'],
      })