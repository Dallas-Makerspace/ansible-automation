#!/usr/bin/env python
"""
Example Usage:
$ INVENTORY_DRIVER=openstack ansible -i inventory machinename -m ping

** Roadmap **
  - AWS Support such as (https://github.com/ansible/ansible/blob/devel/contrib/inventory/ec2.py)
  - Vagrant Support
"""

from __future__ import print_function
from novaclient import client
import os, sys, argparse, subprocess, re

from random import randrange

try:
    import json
except ImportError:
    import simplejson as json

try:
    from requests import RequestException
    import requests_srv as requests
    import srvlookup
except ImportError:
    sys.stderr.write("Please install the requests, requests_srv, and srvlookup modules")
    sys.exit(False)

try:
    from novaclient import client
except ImportError:
    sys.stderr.write("Please install the openstack sdk modules")
    sys.exit(False)



class AnsibleInventory(object):
    """ Base Inventory Object """
    def __init__(self, *args, **kwargs):

        self.__group = "local"
        self.__hosts = ["localhost"]
        self.__vars = {
            "ansible_ssh_user": os.environ.get("USER"),
            "ansible_ssh_port": 22,
            "ansible_ssh_private_key_file": "~/.ssh/id_rsa",
            "ansible_connection": "local"
        }

        self.__inventory = {}
        self.__inventory[self.__group] = {
            "hosts":  self.__hosts,
            "vars": self.__vars
        }

        super(AnsibleInventory, self).__init__(*args, **kwargs)

    def add_inventory(self, node):
        """ build inventory dictionary """

        self.__inventory.update(node)

    def inventory(self, *args):
        """ placeholder for rendering items """

        if args:
            return self.__inventory[args]

        return self.__inventory

    def _render(self):
        """ return json inventory for ansible """
        return json.dumps(self.inventory())

class LocalDriver(AnsibleInventory):
    """ OpenStack Inventory driver for ansible """
    def __init__(self, *args, **kwargs):
        """ returns the local group """
        super(LocalDriver, self).__init__(*args, **kwargs)
        print(self._render())

class CmdbapiDriver(AnsibleInventory):
    """ Restful driver for requesting inventory from cmdbapi """
    def __init__(self, *args, **kwargs):

        self.protocol = kwargs.pop('protocol', 'http')
        self.server = kwargs.pop('server', "inventory")
        self.api = kwargs.pop('api', '/api/v1')
        self.domain = kwargs.pop('domain', 'local')

        self.useragent = kwargs.pop('useragent', 'AnsibleInventory/0.0.1 (ansible 2.2.1.0)')

        try:
            servers = srvlookup.lookup(
                name='ansibleinventory',
                protocol='http',
                domain=self.domain)

            server = servers[randrange(0, len(servers), 1)]
            self.node = "{}:{}".format(server.name, server.port)


        except srvlookup.SRVQueryFailure as error:
            sys.stderr.write("Error: {}\n".format(error))

        super(CmdbapiDriver, self).__init__(*args, **kwargs)

        node = {}

        try:
            results = self.devices()
            for host in results:
                node[host.node_name] = dict(
                    hosts=[ip_address for ip_address in host.ip_addresses],
                    vars=dict(
                        ansible_python_interpreter="/usr/bin/python2",
                        ansible_ssh_user="{}".format("admin")))

                self.add_inventory(node)

        except RequestException as error:
            sys.stderr.write(error.message)

        print(self._render())

    def __endpoint(self, collection):
        return "{}://{}/{}/{}".format(self.protocol, self.server, self.api, collection)

    def devices(self):
        """
        Get data from cmdb
        """

        headers = {
            'useragent': self.useragent
        }

        res = requests.get(
            self.__endpoint('devices?embedded={"ip_addresses":1,"site.name":1}'),
            headers=headers)

        return res.json()['_items']


class DockerDriver(AnsibleInventory):
    """ Generates Inventory from docker machine """
    def __init__(self, *args, **kwargs):

        super(DockerDriver, self).__init__(*args, **kwargs)

        self._dockermachine = None
        self._machine = None

        node = {}

        for machine in self.machines():
            self._machine = machine
            node[machine] = self._node()
            self.add_inventory(node)

        print(self._render())

    def _command(self, *args):
        """ Execute docker-machine within system environment """
        self._dockermachine = subprocess.check_output(["docker-machine"] + list(args)).strip()

    def _inspect(self, value):
        """ executes inspect to return values from docker machine """
        self._command("inspect", "-f", value, self._machine)
        results = self._dockermachine
        return results

    def _node(self):
        """ helper to build node items """
        return dict(
            hosts=[self._inspect("{{.Driver.IPAddress}}")],
            vars=dict(
                ansible_python_interpreter="/usr/bin/python2",
                ansible_ssh_user="{}".format(self._inspect("{{.Driver.SSHUser}}")),
                ansible_ssh_port="{}".format(self._inspect("{{.Driver.SSHPort}}")),
                ansible_ssh_private_key_file="{}".format(self._inspect("{{.Driver.SSHKeyPath}}"))))

    def machines(self):
        """ returns iterable list of machine names from docker-machines """
        self._command("ls", "-q")
        machines = self._dockermachine.splitlines()
        return machines
        
# FIXME: Actually do something better than -
# https://github.com/lukaspustina/dynamic-inventory-for-ansible-with-openstack/blob/master/openstack_inventory.py
class OpenstackDriver(AnsibleInventory):
    """ OpenStack Inventory driver for ansible """
    def __init__(self, *args, **kwargs):
        """ Effectively ```pass``` but do something still """
        super(OpenstackDriver, self).__init__(*args, **kwargs)
        print(self._render())


# FIXME: Actually do something better than -
# gh://ansible/ansible/.../ec2.py
class AwsEc2Driver(AnsibleInventory):
    """ AWS EC2 Inventory driver for ansible """
    def __init__(self, *args, **kwargs):
        """ import modules then effectively ```pass``` but do something still """

        try:
            global ec2
            from boto import ec2
        except ImportError:
            sys.stderr.write("Please install the aws sdk modules")
            sys.exit(False)
            
        super(AwsEc2Driver, self).__init__(*args, **kwargs)
        print(self._render())


class DriverLoadError(Exception):
    """ Alert for loading errors """
    def __init__(self, message, errors):
        self.message = "WARN: driver '{}' was not implemented imported".format(message)
        self.errors = errors

        super(DriverLoadError, self).__init__(message)

class ParserLoadError(Exception):
    """ Alert for loading errors """
    def __init__(self, message, errors):
        self.message = "WARN: Parser '{}' was not implemented imported".format(message)
        self.errors = errors

        super(ParserLoadError, self).__init__(message)

class CommandParser(argparse.ArgumentParser):
    """ Argument parser for command line options """
    def __init__(self, *args, **kwargs):
        self.default_driver = str()
        
        if 'default_driver' in kwargs:
            self.default_driver = kwargs.get('default_driver', 'docker')
            del kwargs['default_driver']

        self.args = argparse.ArgumentParser.__init__(self, description='Produce an Ansible Inventory file based on Docker Machine status')

        self.args.add_argument(
            '-d', '--driver',
            default=os.environ.get("INVENTORY_DRIVER", self.default_driver),
            help="Define which driver to use (default: $INVENTORY_DRIVER or `{}`)".format(self.default_driver))
            
        self.args.add_argument(
            '-l', '--list',
            action='store_true',
            dest='list_operator',
            help='List all active Nods as Ansible inventory items (default: `True`)')

        self.args.add_argument(
            '--host',
            help="Ansible inventory of a particular host",
            action="store",
            dest="ansible_host",
            type=str)
            
        self.args.parse_args()
       
def load_plugin(plugin):
    return dict(
        [(name.lower().split(plugin.lower())[0], cls) for name, cls in
         sys.modules[__name__].__dict__.items() if
         isinstance(cls, type) and re.search('{}$'.format(plugin), name)])

def main():
    """ Loads the drivers, parsers, plugins and then does all the things """

    plugins = {
        "parsers": load_plugin("Parser"),
        "drivers": load_plugin("Drivers")
    }

    args = parsers['command'](default='docker').args

    try:
        plugins['drivers'][args.driver]()
    except KeyError as error:
        raise DriverLoadError(args.driver, error)

if __name__ == "__main__":
    try:
        main()
    except (ParserLoadError, DriverLoadError) as error:
        sys.stderr.write(error.message)
        sys.exit(False)
    finally:
        sys.exit(True)
