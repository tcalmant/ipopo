'''
Created on May 27, 2018

@author: slewis
'''
from pelix.ipopo.decorators import ComponentFactory, Provides, Instantiate
from pelix.rsa.providers.discovery import SERVICE_ENDPOINT_ADVERTISER,\
    EndpointAdvertiser

@ComponentFactory('etcd-endpoint-advertiser-factory')
@Provides(SERVICE_ENDPOINT_ADVERTISER)
@Instantiate('etcd-endpoint-advertiser')
class EtcdEndpointAdvertiser(EndpointAdvertiser):
    
    def _advertise(self,endpoint_description):
        print('advertising ed={0}'.format(endpoint_description))
        return True
    
    def _unadvertise(self,advertised):
        print('unadvertising ed={0}'.format(advertised[0]))
        return True
    
