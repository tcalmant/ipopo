FROM debian

WORKDIR /opt/
RUN apt update && apt install -y curl && apt clean
RUN curl -L  https://github.com/coreos/etcd/releases/download/v2.3.7/etcd-v2.3.7-linux-amd64.tar.gz | tar xzvf -
WORKDIR /opt/etcd-v2.3.7-linux-amd64

ENTRYPOINT [ "/opt/etcd-v2.3.7-linux-amd64/etcd", "--advertise-client-urls", "http://127.0.0.1:12379", "--listen-client-urls", "http://0.0.0.0:12379" ]
