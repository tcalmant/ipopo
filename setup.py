#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --

# ------------------------------------------------------------------------------

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

# ------------------------------------------------------------------------------

import os

def read(fname):
    """
    Utility method to read the content of a whole file
    """
    with open(os.path.join(os.path.dirname(__file__), fname)) as fd:
        return fd.read()

# ------------------------------------------------------------------------------

setup(name='iPOPO',
      version='0.4',
      license='GPLv3',
      description='A service-oriented component model framework',
      long_description=read('README.rst'),
      author='Thomas Calmant',
      author_email='thomas.calmant@gmail.com',
      url='http://ipopo.coderxpress.net/',
      download_url='http://ipopo.coderxpress.net/ipopo-0.4.zip',
      packages=['pelix', 'pelix.ipopo', 'pelix.http', 'pelix.shell'],
      classifiers=[
            'Development Status :: 3 - Alpha',
            'Environment :: Console',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: GNU General Public License (GPL)',
            'Operating System :: OS Independent',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'Topic :: Software Development :: Libraries :: Application Frameworks'
      ]
)
