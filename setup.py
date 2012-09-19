#!/usr/bin/env python
#-- Content-Encoding: UTF-8 --

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(name='iPOPO',
      version='0.3',
      license='GPLv3',
      description='A component model framework',
      author='Thomas Calmant',
      author_email='thomas.calmant@gmail.com',
      url='http://ipopo.coderxpress.net/',
      download_url='http://ipopo.coderxpress.net/ipopo-0.3.zip',
      packages=['pelix', 'pelix.ipopo'],
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
