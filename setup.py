__author__ = 'samantha'

from setuptools import setup, find_packages

packages = find_packages(exclude=['tests'])
setup(name='uoploaders',
      version='0.1',
      description='pkm desktop client',
      author='Samantha Atkins',
      author_email='samantha@sjasoft.com',
      license='internal',
      packages=packages,
      install_requires=['uopclient', 'pytest', 'pytest-asyncio', 'sjautils'],
      zip_safe=False)
