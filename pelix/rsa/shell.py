"""

Remote Service Admin Shell Commands

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
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------
from pelix.ipopo.decorators import ComponentFactory, Provides, \
    Instantiate, Validate, Requires, Property

from pelix.rsa import SERVICE_REMOTE_SERVICE_ADMIN,\
    SERVICE_RSA_EVENT_LISTENER, SERVICE_EXPORTED_CONFIGS, SERVICE_EXPORTED_INTERFACES

from pelix.rsa.remoteserviceadmin import RemoteServiceAdminEvent

from pelix.shell import SERVICE_SHELL_COMMAND

from pelix.rsa.edef import EDEFReader,EDEFWriter
# ------------------------------------------------------------------------------ 
@ComponentFactory('rsa-command-factory')
@Requires('_rsa',SERVICE_REMOTE_SERVICE_ADMIN)
@Provides([SERVICE_SHELL_COMMAND, SERVICE_RSA_EVENT_LISTENER])
@Property('_filename','filename','edef.xml')
@Property('_export_config','export_config','ecf.xmlrpc.server')
@Instantiate('rsa-command')
class RSACommandHandler(object):
    
    def __init__(self):
        self._context = None
        self._rsa = None
        self._edefreader = EDEFReader()
        self._edefwriter = EDEFWriter()
        self._filename = None
        self._export_config = None
    
    @Validate
    def _validate(self,bundle_context):
        self._context = bundle_context
            
    @staticmethod
    def get_namespace():
        return "ecf"

    def get_methods(self):
        return [("importservice", self.import_edef),("exportservice", self.export_edef)]

    def remote_admin_event(self, event):
        if event.get_type() == RemoteServiceAdminEvent.EXPORT_REGISTRATION:
            self._edefwriter.write([event.get_description()], self._filename)
            
    def export_edef(self, io_handler, service_id=None, export_config=None, filename=None):
        if not service_id:
            io_handler.write('Must provide service.id to export as argument.  For example:  exportservice 25\n')
            io_handler.flush()
            return
        svc_ref = self._context.get_service_reference(None,'(service.id='+str(service_id)+')')
        if not svc_ref:
            io_handler.write('Service with id='+str(service_id)+' cannot be found so cannot be exported\n')
            io_handler.flush()
            return
        if export_config:
            self._export_config = export_config
        if filename:
            self._filename = filename
        # Finally export
        self._rsa.export_service(svc_ref,{ SERVICE_EXPORTED_INTERFACES: '*', SERVICE_EXPORTED_CONFIGS: self._export_config })
                
    def import_edef(self, io_handler, edeffile=None):
        if not edeffile:
            edeffile = self._filename
        eds = self._edefreader.parse(open(edeffile, 'r').read())
        for ed in eds:
            self._rsa.import_service(ed)
                


