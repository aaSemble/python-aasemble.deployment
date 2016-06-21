#!/bin/bash

install_consul_upstart_job() {
	mkdir -p /etc/init
	cat <<-EOF > /etc/init/consul.conf
	description "Consul agent"

	start on runlevel [2345]
	stop on runlevel [!2345]

	respawn

	script
	  export GOMAXPROCS=`nproc`

	  if [ -f "/etc/default/consul" ]; then
	    . /etc/default/consul
	  fi

	  exec /usr/sbin/consul agent -config-dir="/etc/consul.d" \${CONSUL_FLAGS}
	end script
	EOF
}

install_consul_template_upstart_job() {
	mkdir -p /etc/init
	cat <<-EOF > /etc/init/consul-template.conf
	description "Consul Template agent"

	start on runlevel [2345]
	stop on runlevel [!2345]

	respawn

	script
	  export GOMAXPROCS=`nproc`

	  if [ -f "/etc/default/consul-template" ]; then
	    . /etc/default/consul-template
	  fi

	  exec /usr/bin/consul-template \${CONSUL_TEMPLATE_FLAGS}
	end script
	EOF
}

install_json_sync() {
    cat <<-EOF > /usr/local/bin/sync-json-from-aasemble
	#!/bin/bash
	if [ "\$1" == "--lock" ]
	then
	    consul lock json-sync "while true; do \$0; sleep 10; done"
	else
	    mkdir -p /var/lib/aaSemble
	    curl ${CLUSTER} | jq -r .json > /var/lib/aaSemble/shared.json
	    curl -X PUT --data-binary @/var/lib/aaSemble/shared.json http://localhost:8500/v1/kv/aaSemble/json
    fi
	EOF
	chmod +x /usr/local/bin/sync-json-from-aasemble
}

install_consul() {
	wget -O consul.zip https://releases.hashicorp.com/consul/0.6.4/consul_0.6.4_linux_amd64.zip
	unzip consul.zip
	mv consul /usr/sbin/consul
	chmod +x /usr/sbin/consul
}

install_consul_template() {
	wget -O consul-template.zip https://releases.hashicorp.com/consul-template/0.14.0/consul-template_0.14.0_linux_amd64.zip
	unzip consul-template.zip
	mv consul-template /usr/bin/consul-template
	chmod +x /usr/bin/consul-template
	mkdir -p /etc/consul-template.d
	echo 'CONSUL_TEMPLATE_FLAGS="-config /etc/consul-template.d"' >> /etc/default/consul-template
}

create_consul_config() {
	mkdir -p /etc/consul.d
	local_ip=$(ip -o route get 8.8.8.8 | sed -e 's/.*src //g' | sed -e 's/ .*//g')
	http --ignore-stdin POST ${CLUSTER}nodes/ cluster=${CLUSTER} internal_ip=${local_ip}

	# Build datacenter value
	sanitized_dc=$(echo ${CLUSTER} | tr -d '.:/-')

	if [ "${SERVER}" = "1" ]
	then
		cat <<-EOF > /etc/consul.d/agent.json
		{
		  "bootstrap_expect": ${NUM_SERVERS},
		  "server": true,
		  "datacenter": "${sanitized_dc}",
		  "advertise_addr": "${local_ip}",
		  "data_dir": "/var/lib/consul"
		}
		EOF
	else
        cat <<-EOF > /etc/consul.d/agent.json
		{
		  "server": false,
		  "datacenter": "${sanitized_dc}",
		  "advertise_addr": "${local_ip}",
		  "data_dir": "/var/lib/consul"
		}
		EOF
	fi
	mkdir -p /var/lib/consul
}

loop_until_cluster_joined() {
	while ! test -f cluster-joined
	do
		if http GET http://localhost:8500/v1/catalog/nodes -b > nodes.json
		then
			if jq .[] < nodes.json
			then
				touch cluster-joined
				continue
			fi
		fi
		http GET ${CLUSTER}nodes/ > cluster.json
		jq '.results[] | .internal_ip | @text' < cluster.json | xargs consul join
		sleep 5
	done
}

install_dnsmasq() {
    apt-get install -y dnsmasq
    echo 'server=/consul/127.0.0.1#8600' >> /etc/dnsmasq.d/10-consul
    /etc/init.d/dnsmasq restart
}

install_docker() {
    curl https://get.docker.com/ | sh
}

do_install() {
    if [ -z "${CLUSTER}" ]
    then
        echo "No CLUSTER environment found. Exiting."
        exit 1
    fi

    apt-get update
    apt-get install -y wget unzip jq httpie

    tmpdir=$(mktemp -d)
    cd "${tmpdir}"

    # Install consul if it's not already there
    if ! which consul
    then
        install_consul
    fi

    if ! which consul-template
    then
        install_consul_template
    fi

    # Create consul config, if it doesn't already exist
    if ! test -d /etc/consul.d
    then
        create_consul_config
    fi

    install_consul_upstart_job

    start consul

    loop_until_cluster_joined

    install_consul_template_upstart_job

    start consul-template

    install_json_sync

    nohup /usr/local/bin/sync-json-from-aasemble --lock &

    install_dnsmasq

    if [ "${INSTALL_DOCKER}" = "1" ]
    then
        install_docker
    fi
}

# This should prevent only running half the script due to curl->sh pipe dying halfway through
do_install
