"""A deployer class to deploy a template on Azure"""
import os.path
import json
from haikunator import Haikunator
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.resources.models import DeploymentMode
#PES
from azure.common.client_factory import get_client_from_cli_profile
import base64

class Deployer(object):
    """ Initialize the deployer class with subscription, resource group and public key.

    :raises IOError: If the public key path cannot be read (access or not exists)
    :raises KeyError: If AZURE_CLIENT_ID, AZURE_CLIENT_SECRET or AZURE_TENANT_ID env
        variables or not defined
    """
    name_generator = Haikunator()

    def __init__(self, subscription_id, resource_group, location,bootstrapfile
                       , vm_name, virtual_network_name
                       , admin_user_name, pub_ssh_key_paths=['~/.ssh/id_rsa.pub']):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.location = location
        self.dns_label_prefix = self.name_generator.haikunate()
        self.vm_name = vm_name
        self.admin_user_name = admin_user_name
        self.virtual_network_name = virtual_network_name

        # Will raise if file not exists or not enough permission
        self.pub_ssh_key = ""
        for pub_ssh_key_path in  pub_ssh_key_paths:
            pub_ssh_key_path = os.path.expanduser(pub_ssh_key_path)
            with open(pub_ssh_key_path, 'r') as pub_ssh_file_fd:
                self.pub_ssh_key = self.pub_ssh_key +  pub_ssh_file_fd.read()
        self.pub_ssh_key = self.pub_ssh_key.strip()
        with open(os.path.abspath(bootstrapfile), 'r') as b_boot:
            script = b_boot.read()
        # 1st encode() string(utf8) to binary, and final decode() is b'' back to string.
        self.bootstrapScriptBase64 = base64.b64encode(script.encode()).decode()

        def get_resource_client():
            from azure.mgmt.resource import ResourceManagementClient
            return get_client_from_cli_profile(ResourceManagementClient)

        try:
            self.credentials = ServicePrincipalCredentials(
                client_id=os.environ['AZURE_CLIENT_ID'],
                secret=os.environ['AZURE_CLIENT_SECRET'],
                tenant=os.environ['AZURE_TENANT_ID']
            )
            self.client = ResourceManagementClient(self.credentials, self.subscription_id)
        except KeyError:
            self.client = get_resource_client()
        except Exception as inst:
            print("type:",type(inst))    # the exception instance
            print("args:",inst.args)     # arguments stored in .args
            print("inst:",inst)
            raise

    def deploy(self,args={}):
        """Deploy the template to a resource group."""
        self.client.resource_groups.create_or_update(
            self.resource_group,
            {
                'location': self.location
            }
        )

        template_path = os.path.join(os.path.dirname(__file__), 'templates', 'template.json')
        with open(template_path, 'r') as template_file_fd:
            template = json.load(template_file_fd)

        parameters = {
            'sshKeyData': self.pub_ssh_key,
            'vmName': self.vm_name,
            'dnsLabelPrefix': self.dns_label_prefix,
            'bootstrapScriptBase64' : self.bootstrapScriptBase64,
            'adminUserName': self.admin_user_name,
            'vmEnvironment': self.resource_group,
            'virtualNetworkName' : self.virtual_network_name

        }
        parameters.update(args) #add args.
        parameters = {k: {'value': v} for k, v in parameters.items()}

        deployment_properties = {
            'mode': DeploymentMode.incremental,
            'template': template,
            'parameters': parameters
        }

        deployment_async_operation = self.client.deployments.create_or_update(
            self.resource_group,
            'azure-sample',
            deployment_properties
        )
        deployment_async_operation.wait()

    def destroy(self):
        """Destroy the given resource group"""
        self.client.resource_groups.delete(self.resource_group)
