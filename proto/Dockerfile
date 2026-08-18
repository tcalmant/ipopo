FROM bufbuild/buf:1.61

RUN apk add --update --no-cache \
    python3 \
    py3-pip \
    && \
  rm -rf /var/cache/apk/* && pip3 install --break-system-packages mypy-protobuf

ENTRYPOINT ["/usr/local/bin/buf"]
