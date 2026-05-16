# Test containers

This folder contains the Docker compositions and configuration files to run tests locally.

## Running tests with SELinux

When your distribution uses SELinux (*e.g.* Fedora), you might need to relabel the files used in the containers to make them readable:

```bash
chcon -t container_file_t xmpp/register_users.sh
chcon -t container_file_t mqtt/mosquitto.conf
```
