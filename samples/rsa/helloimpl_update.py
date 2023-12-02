from pelix.framework import BundleContext
from pelix.ipopo.decorators import ComponentFactory, Instantiate, Validate
from samples.rsa.helloimpl import HelloImpl


@ComponentFactory("remote-hello-consumer-update-factory")
@Instantiate("remote-hello-consumer-update")
class RemoteHelloConsumer:
    @Validate
    def _validate(self, bundle_context: BundleContext) -> None:
        # first register
        registration = bundle_context.register_service(
            "org.eclipse.ecf.examples.hello.IHello",
            HelloImpl(),
            {
                "service.exported.interfaces": "*",
                "service.intents": ["osgi.async"],
                "osgi.basic.timeout": 60000,
            },
        )
        # this will trigger an export update, publish the update via discovery
        # (if any) which will propagate to import side
        registration.set_properties({"one": "myone", "two": 2})
