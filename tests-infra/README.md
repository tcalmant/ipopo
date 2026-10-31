# Test containers

This folder contains the Docker compositions and configuration files to run tests locally.

```bash
sh ./tests-infra/mqtt/prepare.sh
docker compose -f tests-infra/compose.yaml up -d
sh ./tests-infra/xmpp/docker_register_users.sh
```

`mqtt/prepare.sh` generates the secrets of the test MQTT broker, which are never committed: a test CA with the
broker and client certificates (`mqtt/certs`, valid 30 days) and the password of the test user (`mqtt/.env`).
It keeps existing ones: remove them to make new ones, then recreate the broker container.

## Running tests with SELinux

Configuration files are mounted into containers with the `z` flag, which makes them readable even if SELinux is configured (*e.g.* Fedora).

If the composition fails to start due to those volumes, then you might need to relabel the files used in the containers to make them readable:

```bash
chcon -t container_file_t xmpp/register_users.sh
chcon -t container_file_t mqtt/mosquitto.conf
```
