FROM itzg/minecraft-server:java25-graalvm

WORKDIR /app

COPY whitelist.json /data
COPY buildinfo.sh /opt

RUN apt-get update && \
  apt-get install -y --no-install-recommends <package_name> && \
  /opt/buildinfo.sh

EXPOSE 25565 
EXPOSE 24454/udp


