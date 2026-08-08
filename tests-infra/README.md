# Test containers

This folder contains the Docker compositions and configuration files to run tests locally.

## Running tests with SELinux

Configuration files are mounted into containers with the `z` flag, which makes them readable even if SELinux is configured (*e.g.* Fedora).

If the composition fails to start due to those volumes, then you might need to relabel the files used in the containers to make them readable:

```bash
chcon -t container_file_t xmpp/register_users.sh
chcon -t container_file_t mqtt/mosquitto.conf
```
