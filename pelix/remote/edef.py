#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: Beans definition

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1
:status: Alpha

..

    Copyright 2013 isandlaTech

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

# Module version
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# Pelix constants
import pelix.constants
import pelix.remote
import pelix.ldapfilter

# ------------------------------------------------------------------------------

class EndpointDescription(object):
    """
    Endpoint description bean, according to OSGi specifications:
    http://www.osgi.org/javadoc/r4v42/org/osgi/service/remoteserviceadmin/EndpointDescription.html

    This is an importer-side description
    """
    def __init__(self, svc_ref, properties):
        """
        Sets up the description with the given properties

        :raise ValueError: Invalid properties
        """
        # Set up properties
        all_properties = {}
        if svc_ref is not None:
            all_properties.update(svc_ref.get_properties())

        if properties:
            all_properties.update(properties)

        # Add  some properties if the service reference is given
        if svc_ref is not None:
            # Service ID
            all_properties[pelix.remote.PROP_ENDPOINT_SERVICE_ID] = \
                                svc_ref.get_property(pelix.constants.SERVICE_ID)

            # TODO: Framework UUID ??

        self.__check_properties(properties)

        # Keep a copy of properties
        self.__properties = properties.copy()


    def __str__(self):
        """
        String representation
        """
        return "EndpointDescription(id={0}; endpoint.service.id={1}; " \
               "framework.uuid={2})".format(self.get_id(),
                                            self.get_service_id(),
                                            self.get_framework_uuid())


    def __check_properties(self, props):
        """
        Checks that the given dictionary doesn't have export keys and has
        import keys

        :param props: Properties to validate
        :raise ValueError: Invalid properties
        """
        # Mandatory properties
        mandatory = (pelix.remote.PROP_ENDPOINT_ID,
                     pelix.remote.PROP_IMPORTED_CONFIGS,
                     pelix.constants.OBJECTCLASS)
        for key in mandatory:
            if key not in props:
                raise ValueError("Missing property: {0}".format(key))

        # Export/Import properties
        props_export = (pelix.remote.PROP_EXPORTED_CONFIGS,
                        pelix.remote.PROP_EXPORTED_INTERFACES)

        for key in props_export:
            if key in props:
                raise ValueError("Export property found: {0}".format(key))


    def get_configuration_types(self):
        """
        Returns the configuration types.

        A distribution provider exports a service with an endpoint.
        This endpoint uses some kind of communications protocol with a set of
        configuration parameters.
        There are many different types but each endpoint is configured by only
        one configuration type.
        However, a distribution provider can be aware of different configuration
        types and provide synonyms to increase the change a receiving
        distribution provider can create a connection to this endpoint.
        This value of the configuration types is stored in the
        pelix.remote.PROP_IMPORTED_CONFIGS service property.

        :return: The configuration types (list of str)
        """
        # Return a copy of the list
        return self.__properties[pelix.remote.PROP_IMPORTED_CONFIGS][:]


    def get_framework_uuid(self):
        """
        Returns the UUID of the framework exporting this endpoint, or None

        :return: A framework UUID (str) or None
        """
        return self.__properties.get(pelix.remote.PROP_ENDPOINT_FRAMEWORK_UUID)


    def get_id(self):
        """
        Returns the endpoint's id.
        """
        return self.__properties[pelix.remote.PROP_ENDPOINT_ID]


    def get_intents(self):
        """
        Returns the list of intents implemented by this endpoint.

        The intents are based on the service.intents on an imported service,
        except for any intents that are additionally provided by the importing
        distribution provider.
        All qualified intents must have been expanded.
        This value of the intents is stored in the
        pelix.remote.PROP_INTENTS service property.

        :return: A list of intents (list of str)
        """
        # Return a copy of the list
        try:
            return self.__properties[pelix.remote.PROP_INTENTS][:]
        except KeyError:
            return []


    def get_interfaces(self):
        """
        Provides the list of interfaces implemented by the exported service.

        :return: A list of specifications (list of str)
        """
        return self.__properties[pelix.constants.OBJECTCLASS][:]


    def get_package_version(self, package):
        """
        Provides the version of the given package name.

        :param package: The name of the package
        :return: The version of the specified package as a tuple or (0,0,0)
        """
        name = "{0}{1}".format(pelix.remote.PROP_ENDPOINT_PACKAGE_VERSION_,
                               package)
        try:
            # Get the version string
            version = self.__properties[name]

            # Split dots ('.')
            return tuple(version.split('.'))

        except KeyError:
            # No version
            return (0, 0, 0)


    def get_properties(self):
        """
        Returns all endpoint properties.

        :return: A copy of the endpoint properties
        """
        return self.__properties.copy()


    def get_service_id(self):
        """
        Returns the service id for the service exported through this endpoint.

        :return: The ID of service on the exporter side, or 0
        """
        try:
            return self.__properties[pelix.remote.PROP_ENDPOINT_SERVICE_ID]
        except KeyError:
            # Not found
            return 0


    def is_same_service(self, endpoint):
        """
        Tests if this endpoint and the given one have the same framework UUID
        and service ID

        :param endpoint: Another endpoint
        :return: True if both endpoints represent the same remote service
        """
        return self.get_framework_uuid() == endpoint.get_framework_uuid() \
            and self.get_service_id() == endpoint.get_service_id()


    def matches(self, ldap_filter):
        """
        Tests the properties of this EndpointDescription against the given
        filter

        :param ldap_filter: A filter
        :return: True if properties matches the filter
        """
        return pelix.ldapfilter.get_ldap_filter(ldap_filter)\
                                                    .matches(self.__properties)
