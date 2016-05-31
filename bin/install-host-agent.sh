#!/bin/bash
if [ -z "${CLUSTER}" ]
then
    echo "No CLUSTER environment found. Exiting."
    exit 1
fi

apt-get install wget unzip jq httpie

tmpdir=$(mktemp -d)
cd "${tmpdir}"

# Install consul if it's not already there
if ! which consul
then
    wget -O consul.zip https://releases.hashicorp.com/consul/0.6.4/consul_0.6.4_linux_amd64.zip
    unzip consul.zip
    mv consul /usr/sbin/consul
    chmod +x /usr/sbin/consul
fi

if ! which consul-template
then
    wget -O consul-template.zip https://releases.hashicorp.com/consul-template/0.14.0/consul-template_0.14.0_linux_amd64.zip
    unzip consul-template.zip
    mv consul-template /usr/bin/consul-template
    chmod +x /usr/bin/consul-template
fi


# Create consul config, if it doesn't already exist
if ! test -d /etc/consul.d
then
    mkdir -p /etc/consul.d
    local_ip=$(ip -o route get 8.8.8.8 | sed -e 's/.*src //g' | sed -e 's/ .*//g')
    http --ignore-stdin POST ${CLUSTER}nodes/ cluster=${CLUSTER} internal_ip=${local_ip}

    # Build datacenter value
    sanitized_dc=$(echo ${CLUSTER} | tr -d '.:/-')

    if [ "${SERVER}" = "1" ]
    then
        cat << EOF > /etc/consul.d/agent.json
        {
          "bootstrap_expect": ${NUM_SERVERS},
          "server": true,
          "datacenter": "${sanitized_dc}",
          "data_dir": "/var/lib/consul"
        }
EOF
    else
        cat << EOF > /etc/consul.d/agent.json
        {
          "server": false,
          "datacenter": "${sanitized_dc}",
          "data_dir": "/var/lib/consul"
        }
EOF
    fi
    mkdir -p /var/lib/consul
fi

consul agent -config-dir=/etc/consul.d &

while ! test -f cluster-joined
do
    if http GET http://localhost:8500/v1/catalog/nodes -b > nodes.json
    then
        if jq .[] < nodes.json
        then
            touch cluster-joined
            break
        fi
    fi
    http GET ${CLUSTER}nodes/ > cluster.json
    jq '.results[] | .internal_ip | @text' < cluster.json | xargs consul join
    sleep 5
done
