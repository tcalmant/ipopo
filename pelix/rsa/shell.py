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
from threading import RLock
from traceback import print_exception
_logger = logging.getLogger(__name__)
# ------------------------------------------------------------------------------
# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)
# Documentation strings format
__docformat__ = "restructuredtext en"
# ------------------------------------------------------------------------------
from pelix.ipopo.decorators import ComponentFactory, Provides, \
    Instantiate, Validate, Requires, Property, BindField, UnbindField

from pelix.rsa import SERVICE_REMOTE_SERVICE_ADMIN,\
    SERVICE_EXPORTED_CONFIGS, SERVICE_EXPORTED_INTERFACES,\
    SERVICE_IMPORT_DISTRIBUTION_PROVIDER, SERVICE_EXPORT_DISTRIBUTION_PROVIDER,\
    SERVICE_EXPORT_CONTAINER, SERVICE_IMPORT_CONTAINER

from pelix.rsa.remoteserviceadmin import RemoteServiceAdminEvent

from pelix.shell import SERVICE_SHELL_COMMAND

from pelix.rsa.edef import EDEFReader,EDEFWriter

def _full_class_name(o):
    module = o.__class__.__module__
    if module is None or module == str.__class__.__module__:
        return o.__class__.__name__
    return module + '.' + o.__class__.__name__

# ------------------------------------------------------------------------------ 
@ComponentFactory('rsa-command-factory')
@Requires('_rsa',SERVICE_REMOTE_SERVICE_ADMIN)
@Requires('_imp_containers',SERVICE_IMPORT_CONTAINER,True,True)
@Requires('_exp_containers',SERVICE_EXPORT_CONTAINER,True,True)
@Requires('_imp_dist_providers',SERVICE_IMPORT_DISTRIBUTION_PROVIDER,True,True)
@Requires('_exp_dist_providers',SERVICE_EXPORT_DISTRIBUTION_PROVIDER,True,True)
@Provides([SERVICE_SHELL_COMMAND])
@Property('_edef_filename','filename','edef.xml')
@Property('_export_config','export_config','ecf.xmlrpc.server')
@Instantiate('rsa-command')
class RSACommandHandler(object):
    
    SHELL_NAMESPACE = 'rsa'
    EXPIMP_LINE_FORMAT = '{0:<37}|{1:<43}|{2:<3}\n'
    
    CONTAINER_LINE_FORMAT = '{0:<45}|{1:<40}\n'
    CONTAINER_FORMAT = 'ID={0}\n\tNamespace={1}\n\tClass={2}\n\tConnectedTo={3}\n\tConnectNamespace={4}\n\tConfig Type/Distribution Provider={5}\n'
    CONTAINER_TABLE_COLUMNS = ['Container ID/instance.name','Class']
    PROVIDER_FORMAT = 'ID={0}\n\tSupported Configs={1}\n\tSupportedIntents={2}\n'
    PROVIDER_TABLE_COLUMNS = ['Distribution Provider/Config','Class']
    
    def __init__(self):
        self._context = None
        self._rsa = None
        self._imp_containers = []
        self._exp_containers = []
        self._imp_dist_providers = []
        self._imp_dist_providers = []
        self._edef_filename = None
        self._default_export_config = None
        self._bind_lock = RLock()

    def _bind_lists(self,field,service):
        with self._bind_lock:
            field.append(service)
    
    def _unbind_lists(self,field,service):
        with self._bind_lock:
            try:
                field.remove(service)
            except:
                pass
            
    @BindField('_imp_containers')
    def _bind_imp_containers(self,field,service,service_ref):
        self._bind_lists(self._imp_containers,service)
            
    @UnbindField('_imp_containers')
    def _unbind_imp_containers(self,field,service,service_ref):
        self._unbind_lists(self._imp_containers, service)

    @BindField('_exp_containers')
    def _bind_exp_containers(self,field,service,service_ref):
        self._bind_lists(self._exp_containers,service)
            
    @UnbindField('_exp_containers')
    def _unbind_exp_containers(self,field,service,service_ref):
        self._unbind_lists(self._exp_containers, service)

    @BindField('_imp_dist_providers')
    def _bind_imp_dist_providers(self,field,service,service_ref):
        self._bind_lists(self._imp_dist_providers,service)
            
    @UnbindField('_imp_dist_providers')
    def _unbind_imp_dist_providers(self,field,service,service_ref):
        self._unbind_lists(self._imp_dist_providers, service)

    @BindField('_exp_dist_providers')
    def _bind_exp_dist_providers(self,field,service,service_ref):
        self._bind_lists(self._exp_dist_providers,service)
            
    @UnbindField('_exp_dist_providers')
    def _unbind_exp_dist_providers(self,field,service,service_ref):
        self._unbind_lists(self._exp_dist_providers, service)

    def _get_containers(self,containerid=None):
        with self._bind_lock:
            containers = list(set(self._imp_containers+self._exp_containers))
            if containerid:
                return [c for c in containers if c.get_id() == containerid]
            else:
                return containers
    
    def _get_dist_providers(self,providerid=None):
        with self._bind_lock:
            providers = list(set(self._imp_dist_providers+self._exp_dist_providers))
            if providerid:
                return [p for p in providers if p.get_config_name() == providerid]
            return providers
        
    @Validate
    def _validate(self,bundle_context):
        self._context = bundle_context
            
    @staticmethod
    def get_namespace():
        return RSACommandHandler.SHELL_NAMESPACE

    def get_methods(self):
        return [("listconfigs",self._list_providers),
                ("lcfgs",self._list_providers),
                ("listproviders",self._list_providers),
                ("listcontainers",self._list_containers),
                ("lcs",self._list_containers),
                ("listexports",self._list_exported_configs),
                ("listimports",self._list_imported_configs),
                ("lexps",self._list_exported_configs),
                ("limps",self._list_imported_configs),
                ("importservice", self.import_edef),
                ("impsvc", self.import_edef),
                ("exportservice", self.export_edef),
                ("exportsvc", self.export_edef),
                ("unimportservice", self.unimport),
                ("unimpsvc", self.unimport),
                ("unexportservice", self.unexport),
                ("unexpsvc", self.unexport)]

    def remote_admin_event(self, event):
        if event.get_type() == RemoteServiceAdminEvent.EXPORT_REGISTRATION:
            self._edefwriter.write([event.get_description()], self._edef_filename)
    
    def _list_providers(self, io_handler, providerid=None):
        with self._bind_lock:
            providers = self._get_dist_providers(providerid)
        if len(providers) > 0:
            if providerid:
                provider = providers[0]
                io_handler.write(self.PROVIDER_FORMAT.format(provider.get_config_name(),
                                                             provider.get_supported_configs(),
                                                             provider.get_supported_intents()))
            else:
                io_handler.write(self.CONTAINER_LINE_FORMAT.format(*self.PROVIDER_TABLE_COLUMNS))
                for p in providers:
                    io_handler.write(self.CONTAINER_LINE_FORMAT.format(p.get_config_name(),_full_class_name(p)))

                
    def _list_containers(self, io_handler, containerid=None):
        with self._bind_lock:
            containers = self._get_containers(containerid)
        if len(containers) > 0:
            if containerid:
                container = containers[0]
                connected_id = container.get_connected_id()
                ns = container.get_namespace()
                io_handler.write(self.CONTAINER_FORMAT.format(container.get_id(),ns,_full_class_name(container),
                                                              connected_id,ns,container.get_config_name()))
            else:   
                io_handler.write(self.CONTAINER_LINE_FORMAT.format(*self.CONTAINER_TABLE_COLUMNS))
                for c in containers:
                    io_handler.write(self.CONTAINER_LINE_FORMAT.format(c.get_id(),_full_class_name(c)))
            
    def _list_configs(self, io_handler, expimp, endpoint_id=None):
        configs = expimp[0]()
        if endpoint_id:
            matching_eds = [x.get_description() for x in configs if x.get_description().get_id() == endpoint_id]
            if len(matching_eds) > 0:
                io_handler.write('Endpoint description for endpoint.id={0}:\n'.format(endpoint_id))
                io_handler.write(EDEFWriter().to_string(matching_eds))
        else:
            io_handler.write(self.EXPIMP_LINE_FORMAT.format('endpoint.id',expimp[1]+' Container ID',expimp[1]+' Service Id'))
            for export_reg in configs:
                ed = export_reg.get_description()
                io_handler.write(self.EXPIMP_LINE_FORMAT.format(str(ed.get_id()),str(ed.get_container_id()[1]),ed.get_service_id()))
        io_handler.write('\n')
    
    def _list_exported_configs(self, io_handler, endpoint_id=None):  
        self._list_configs(io_handler,(self._rsa._get_export_regs,'Export'),endpoint_id)
        
    def _list_imported_configs(self, io_handler, endpoint_id=None):
        self._list_configs(io_handler,(self._rsa._get_import_regs,'Import'),endpoint_id)
    
    def unimport(self, io_handler, endpointid):
        import_regs = self._rsa._get_import_regs()
        found_reg = None
        for import_reg in import_regs:
            ed = import_reg.get_description()
            if ed and ed.get_id() == endpointid:
                found_reg = import_reg
        if not found_reg:
            io_handler.write('Cannot find import registration with endpoint.id='+endpointid)
            io_handler.flush()
            return
        # now close it
        found_reg.close()

    def unexport(self, io_handler, endpointid):
        export_regs = self._rsa._get_export_regs()
        found_reg = None
        for export_reg in export_regs:
            ed = export_reg.get_description()
            if ed and ed.get_id() == endpointid:
                found_reg = export_reg
        if not found_reg:
            io_handler.write('Cannot find export registration with endpoint.id='+endpointid)
            io_handler.flush()
            return
        # now close it
        found_reg.close()


    def export_edef(self, io_handler, service_id, export_config=None, filename=None):
        svc_ref = self._context.get_service_reference(None,'(service.id={0})'.format(service_id))
        if not svc_ref:
            io_handler.write('Service with id={0} cannot be found so no service can be exported\n'.format(service_id))
            io_handler.flush()
            return
        if export_config:
            self._export_config = export_config
        if filename:
            self._edef_filename = filename
        io_handler.write('Exporting service={0} using config={1} to file={2}\n'.format(svc_ref,self._export_config,self._edef_filename))
        io_handler.flush()
        # Finally export
        export_regs = self._rsa.export_service(svc_ref,{ SERVICE_EXPORTED_INTERFACES: '*', SERVICE_EXPORTED_CONFIGS: self._export_config })
        for export_reg in export_regs:
            exp = export_reg.get_exception()
            if exp:      
                io_handler.write('\nException exporting service={0}.  Exception stack:\n'.format(export_reg.get_reference()))
                print_exception(exp[0],exp[1],exp[2],limit=None, file=io_handler)  
            else:
                io_handler.write('\nService={0} exported.  Endpoint description:\n'.format(export_reg.get_reference()))
                io_handler.write(EDEFWriter().to_string([export_reg.get_description()]))
            io_handler.write('\n')
        io_handler.flush()

    def import_edef(self, io_handler, edeffile=None):
        if not edeffile:
            edeffile = self._edef_filename
        io_handler.write('Importing from EDEF file={0}\n'.format(edeffile))
        eds = EDEFReader().parse(open(edeffile, 'r').read())
        for ed in eds:
            import_reg = self._rsa.import_service(ed)
            if import_reg:
                exp = import_reg.get_exception()
                if exp:
                    io_handler.write('Exception importing endpoint.id={0}\n'.format(import_reg.get_description.get_id()))
                    print_exception(exp[0],exp[1],exp[2],limit=None, file=io_handler)  
                else:
                    io_handler.write('Service={0} imported\n'.format(import_reg.get_reference()))
                    io_handler.write(EDEFWriter().to_string([import_reg.get_description()]))
                io_handler.write('\n')
                io_handler.flush()

