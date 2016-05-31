# aaSemble Deployment Engine

![Travis status](https://travis-ci.org/aaSemble/python-aasemble.deployment.svg)

This is the aaSemble Deployment Engine. It's a cloud centric deployment engine
that aims to facilitate deployment for both ephemeral environments (for
integration testing) as well for long-lived environments.

aaSemble Deployment Engine reads a YAML file describing your service's
architecture. Let's look at an example.

    nodes:
      lb:
        flavor: proxy
        image: trusty
        disk: 10
        security_groups:
          - www
        script: |
          #!/bin/bash -x
          curl https://aasemble.com/installer/current/install.sh | CLUSTER=${cluster} bash
          apt-get install -y haproxy
          wget -O /etc/haproxy/haproxy.cfg.tmpl https://raw.githubusercontent.com/aaSemble/python-aasemble.deployment/master/examples/simple/haproxy.cfg.tmpl
          sed -i -e 's/ENABLED=0/ENABLED=1/g' /etc/default/haproxy
          consul-template -template "/etc/haproxy/haproxy.cfg.tmpl:/etc/haproxy/haproxy.cfg:/etc/init.d/haproxy reload"
      web:
        count: 3
        flavor: web
        image: trusty
        disk: 10
        securitygroups:
          default
        script: |
          #!/bin/bash -x
          curl https://aasemble.com/installer/current/install.sh | CLUSTER=${cluster} NUM_SERVERS=3 SERVER=1 bash
          apt-get install -y nginx
          wget -O /etc/consul.d/www.json https://raw.githubusercontent.com/aaSemble/python-aasemble.deployment/master/examples/simple/www.json
          consul reload
          hostname > /usr/share/nginx/html/hostname.txt
    security_groups:
      www:
      - cidr: 0.0.0.0/0
        from_port: 80
        to_port: 80
        protocol: tcp

Starting from the top, we have a section called `nodes`. This is where
we define our nodes.  We define a node called "lb" and another called
"web". The web node has `count: 3`, so we're actually launching three
of those. They'll be named "web1", "web2", and "web3".

Both types of nodes specify a flavor. The "lb" variety uses a flavor
called "proxy" and the "web" variety uses a flavor called "web". This
lets users choose appropriate flavors for their deployment target.
On some clouds you may want to use a general purpose flavor for your
proxy, while other clouds might provide an instance flavor that is
optimised for high throughput.

Both types specify a generic image called "trusty". We generally prefer
to use generic base images and perform customisations on boot.

Both types also specify a boot disk size of 10GB.

The load balancer instance has a security group called "www", while the
web instances have a security group called "default". You can see the
www security group being defined further down to allow traffic from
everywhere to port 80.

To bootstrap the nodes, we pass in a script that will be run at boot
time. First, we install the aaSemble host agent. We pass in a `cluster`
which helps the agent locate the other members of the cluster.

Once bootstrapped, the nodes have a working consul cluster, can send
events, register services, etc. In our example, we make the web nodes
register a service with Consul and haproxy on the load balancer nodes
use that information from Consul to build their configuration.

Once launched, you should be able to query the load balancer and fetch
`hostname.txt` from it and have it show `web1`, `web2`, `web3` in a
round-robin fashion.


Let's take it for a spin, shall we?

For this demo, we're assuming you're using Google Compute Engine. Create
a new project for this and download a JSON file with the credentials.

Create a gce.ini with the following contents:

    [connection]
    driver = gce
    key_file = credentials.json
    location = us-central1-f
    username = soren
    sshkey = ~/.ssh/id_rsa.pub

    [flavors]
    proxy = n1-standard-1
    web = n1-standard-1

    [images]
    trusty = ubuntu-1404-trusty-v20160516

We create a new cluster on the aaSemble node tracker:

    $ curl -X POST https://aasemble.com/api/devel/clusters/ -d ' ' -s | python -m json.tool
    {
        "nodes": "https://aasemble.com/api/devel/clusters/12345508-4395-42cb-98bf-5d8c60faba3e/nodes/",
        "self": "https://aasemble.com/api/devel/clusters/12345508-4395-42cb-98bf-5d8c60faba3e/"
    }

We pass the cluster ID into the deployment tool:

    $ aasemble apply gce.ini examples/simple/resources.yaml

...and you sit back and watch the magic happen.
