#!/usr/bin/python
# -- Content-Encoding: UTF-8 --
"""

BasicTopologyManager implements TopologyManager API

:author: Scott Lewis
:copyright: Copyright 2018, Scott Lewis
:license: Apache License 2.0
:version: 0.1.0

..

    Copyright 2018 Scott Lewis

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""
# ------------------------------------------------------------------------------
# Standard logging
import logging
from pelix.rsa import ECF_ENDPOINT_CONTAINERID_NAMESPACE
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------
# Ipopo decorator constants
from pelix.ipopo.decorators import ComponentFactory, Instantiate
# TopologyManager class from topologymanagers API
from pelix.rsa.topologymanagers import TopologyManager
# ------------------------------------------------------------------------------
@ComponentFactory('basic-topology-manager-factory')
# Tell iPOPO to instantiate a component instance as soon as the file is loaded
@Instantiate('basic-topology-manager', { TopologyManager.ENDPOINT_LISTENER_SCOPE:'('+ECF_ENDPOINT_CONTAINERID_NAMESPACE+'=*)'})
class BasicTopologyManager(TopologyManager):
    '''BasicTopologyManager extends TopologyManager api.  No override is
    required, but __init__ is notified for logging
    '''
    def __init__(self):
        super(BasicTopologyManager,self).__init__()
        _logger.debug('BasicToplogyManager.__<init>__')

