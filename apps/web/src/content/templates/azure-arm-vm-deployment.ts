import type { Template } from '@/content/types';

export const template: Template = {
  meta: {
    id: 'azure-arm-vm-deployment',
    slug: 'azure-arm-vm-deployment',
    title: 'Azure ARM Template — Linux VM Deployment',
    description:
      'An ARM deployment template that provisions a Linux virtual machine end to end — virtual network, subnet, public IP, network interface and the VM itself — the common single-VM starting point.',
    category: 'Cloud',
    provider: 'Azure',
    difficulty: 'intermediate',
    estimatedReadTime: '7 min',
    tags: ['azure', 'arm', 'iac', 'virtual-machine', 'vnet', 'deployment'],
    schemaVersion: '2019-04-01',
    featured: true,
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    starterPrompts: [
      'Add a data disk to the virtual machine',
      'Change the VM size to Standard_D2s_v5',
      'Add a network security group allowing SSH',
      'Output the public IP address',
    ],
    relatedTemplates: ['azure-arm-template', 'terraform-json'],
    relatedBlogs: ['azure-arm-vm-deployment-explained'],
    purpose:
      'Deploy a self-contained Linux VM with its networking stack (VNet, subnet, public IP, NIC) from a single declarative ARM template.',
    whenToUse:
      'Standing up a dev/test VM, a bastion host, or a template you clone per environment via `az deployment group create`.',
    requiredFields: [
      '$schema — the ARM template schema URL',
      'contentVersion — your template version string',
      'resources — VNet, publicIP, NIC and the virtualMachine',
    ],
    optionalFields: [
      'parameters — adminUsername, vmSize, sshPublicKey supplied at deploy time',
      'variables — computed names and the subnet resource id',
      'outputs — the public IP or FQDN returned after deployment',
    ],
    bestPractices: [
      'Use SSH public keys, not passwords, for the admin login.',
      'Parameterize vmSize and location so one template serves every environment.',
      'Pin apiVersion per resource type; do not float it.',
    ],
    security: [
      'Never hardcode credentials; pass sshPublicKey as a parameter or Key Vault reference.',
      'Attach a network security group and restrict SSH (22) to known source ranges.',
      'Prefer a bastion or just-in-time access over a public IP on production VMs.',
    ],
  },
  json: {
    $schema:
      'https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#',
    contentVersion: '1.0.0.0',
    parameters: {
      adminUsername: {
        type: 'string',
        metadata: { description: 'Admin username for the VM' },
      },
      sshPublicKey: {
        type: 'securestring',
        metadata: { description: 'SSH RSA public key for the admin user' },
      },
      vmSize: {
        type: 'string',
        defaultValue: 'Standard_B2s',
      },
      location: {
        type: 'string',
        defaultValue: '[resourceGroup().location]',
      },
    },
    variables: {
      vnetName: 'vnet-app',
      subnetName: 'subnet-app',
      publicIpName: 'pip-app',
      nicName: 'nic-app',
      vmName: 'vm-app',
      subnetRef:
        "[resourceId('Microsoft.Network/virtualNetworks/subnets', variables('vnetName'), variables('subnetName'))]",
    },
    resources: [
      {
        type: 'Microsoft.Network/virtualNetworks',
        apiVersion: '2023-05-01',
        name: "[variables('vnetName')]",
        location: "[parameters('location')]",
        properties: {
          addressSpace: { addressPrefixes: ['10.0.0.0/16'] },
          subnets: [
            {
              name: "[variables('subnetName')]",
              properties: { addressPrefix: '10.0.0.0/24' },
            },
          ],
        },
      },
      {
        type: 'Microsoft.Network/publicIPAddresses',
        apiVersion: '2023-05-01',
        name: "[variables('publicIpName')]",
        location: "[parameters('location')]",
        properties: { publicIPAllocationMethod: 'Static' },
        sku: { name: 'Standard' },
      },
      {
        type: 'Microsoft.Network/networkInterfaces',
        apiVersion: '2023-05-01',
        name: "[variables('nicName')]",
        location: "[parameters('location')]",
        dependsOn: [
          "[resourceId('Microsoft.Network/virtualNetworks', variables('vnetName'))]",
          "[resourceId('Microsoft.Network/publicIPAddresses', variables('publicIpName'))]",
        ],
        properties: {
          ipConfigurations: [
            {
              name: 'ipconfig1',
              properties: {
                privateIPAllocationMethod: 'Dynamic',
                subnet: { id: "[variables('subnetRef')]" },
                publicIPAddress: {
                  id: "[resourceId('Microsoft.Network/publicIPAddresses', variables('publicIpName'))]",
                },
              },
            },
          ],
        },
      },
      {
        type: 'Microsoft.Compute/virtualMachines',
        apiVersion: '2023-09-01',
        name: "[variables('vmName')]",
        location: "[parameters('location')]",
        dependsOn: [
          "[resourceId('Microsoft.Network/networkInterfaces', variables('nicName'))]",
        ],
        properties: {
          hardwareProfile: { vmSize: "[parameters('vmSize')]" },
          osProfile: {
            computerName: "[variables('vmName')]",
            adminUsername: "[parameters('adminUsername')]",
            linuxConfiguration: {
              disablePasswordAuthentication: true,
              ssh: {
                publicKeys: [
                  {
                    path: "[concat('/home/', parameters('adminUsername'), '/.ssh/authorized_keys')]",
                    keyData: "[parameters('sshPublicKey')]",
                  },
                ],
              },
            },
          },
          storageProfile: {
            imageReference: {
              publisher: 'Canonical',
              offer: '0001-com-ubuntu-server-jammy',
              sku: '22_04-lts-gen2',
              version: 'latest',
            },
            osDisk: {
              createOption: 'FromImage',
              managedDisk: { storageAccountType: 'Premium_LRS' },
            },
          },
          networkProfile: {
            networkInterfaces: [
              {
                id: "[resourceId('Microsoft.Network/networkInterfaces', variables('nicName'))]",
              },
            ],
          },
        },
      },
    ],
    outputs: {
      adminUsername: {
        type: 'string',
        value: "[parameters('adminUsername')]",
      },
    },
  },
};
