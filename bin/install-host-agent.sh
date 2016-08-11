#!/bin/bash

install_dnsmasq() {
    mkdir -p /etc/dnsmasq.d
    echo 'server=/consul/127.0.0.1#8600' >> /etc/dnsmasq.d/10-consul
    apt-get install -y dnsmasq
    sleep 2
}

install_docker() {
    apt-get install -y screen
    screen -dm 'curl https://get.docker.com/ | sh'
}

launch_host_agent() {
    mkdir -p /etc/consul.d
    docker run --name=aasemble-host-agent \
               -e CLUSTER=${CLUSTER} \
               -e AASEMBLE_HOST_AGENT=${AASEMBLE_HOST_AGENT} \
               -e CONSUL_SERVER=${CONSUL_SERVER} \
               -e CONSUL_SERVERS=${CONSUL_SERVERS} \
               -v /var/run/docker.sock:/var/run/docker.sock \
               --net=host \
               --restart=always \
               -d \
               ${AASEMBLE_HOST_AGENT:-aasemble/hostagent}
}

do_install() {
    if [ -z "${CLUSTER}" ]
    then
        echo "No CLUSTER environment found. Exiting."
        exit 1
    fi

    install_docker
    launch_host_agent
    install_dnsmasq
}

# This should prevent only running half the script due to curl->sh pipe dying halfway through
do_install
