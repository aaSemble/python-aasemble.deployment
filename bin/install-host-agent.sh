#!/bin/bash

install_docker() {
    apt-get install -y screen
    screen -dmS dockerinstall sh -c 'curl https://get.docker.com/ | sh'
}

install_and_launch_finish_install_script() {
    cat > /tmp/finish-install.sh <<EOF
#!/bin/sh -x

exec > /tmp/finish-install.log 2>&1

wait_for_docker() {
    while ! docker ps
    do
        echo 'Docker not ready'
        sleep 2
    done
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

install_dnsmasq() {
    mkdir -p /etc/dnsmasq.d
    echo 'server=/consul/127.0.0.1#8600' >> /etc/dnsmasq.d/10-consul
    apt-get install -y dnsmasq
    sleep 2
}

finish_install() {
    wait_for_docker
    launch_host_agent
    install_dnsmasq
    rm /tmp/finish-install.sh
}

finish_install
EOF
    chmod +x /tmp/finish-install.sh
    /tmp/finish-install.sh &
}

do_install() {
    if [ -z "${CLUSTER}" ]
    then
        echo "No CLUSTER environment found. Exiting."
        exit 1
    fi

    install_docker
    install_and_launch_finish_install_script
}

# This should prevent only running half the script due to curl->sh pipe dying halfway through
do_install
