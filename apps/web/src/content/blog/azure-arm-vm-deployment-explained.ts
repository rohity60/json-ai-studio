import type { BlogPost } from '@/content/types';

export const post: BlogPost = {
  meta: {
    slug: 'azure-arm-vm-deployment-explained',
    title: 'Deploying a Linux VM with an ARM Template',
    description:
      'How the pieces of an ARM VM deployment fit together — virtual network, subnet, public IP, network interface and the VM — and why the resources depend on each other in that order.',
    updatedAt: '2026-07-18',
    author: 'JSON AI Studio',
    tags: ['azure', 'arm', 'virtual-machine', 'iac'],
    readingTime: '6 min',
    aiSummary:
      'An ARM VM deployment is five resources: a virtual network with a subnet, a public IP, a network interface that binds the two, and the VM that consumes the NIC. dependsOn enforces creation order. Use SSH keys, parameterize vmSize and location, and pin apiVersion per resource.',
    relatedTemplates: ['azure-arm-vm-deployment'],
    relatedBlogs: [],
    faq: [
      {
        q: 'Why do I need a NIC as a separate resource?',
        a: 'A VM does not attach to a subnet directly. The network interface binds the VM to a subnet and (optionally) a public IP, so it must exist before the VM references it.',
      },
      {
        q: 'How do I deploy this template?',
        a: 'az deployment group create --resource-group my-rg --template-file azuredeploy.json --parameters adminUsername=azureuser sshPublicKey="$(cat ~/.ssh/id_rsa.pub)".',
      },
    ],
  },
  body: `An ARM template that "creates a VM" is really deploying **five** resources that have to line up in the right order. Here is what each one does and why the dependencies matter.

## The five resources

1. **Virtual network** — the private address space (\`10.0.0.0/16\`) your VM lives in.
2. **Subnet** — a slice of that space (\`10.0.0.0/24\`); declared inside the VNet.
3. **Public IP** — an internet-facing address, \`Static\` with the \`Standard\` SKU.
4. **Network interface (NIC)** — binds the subnet and public IP together into one ipConfiguration.
5. **Virtual machine** — consumes the NIC and boots from an image.

## Order matters: dependsOn

ARM parallelizes deployment, so you must declare ordering explicitly. The NIC needs the VNet and public IP first:

\`\`\`json
"dependsOn": [
  "[resourceId('Microsoft.Network/virtualNetworks', variables('vnetName'))]",
  "[resourceId('Microsoft.Network/publicIPAddresses', variables('publicIpName'))]"
]
\`\`\`

and the VM waits on the NIC. Skip these and the deploy fails intermittently.

## Log in with keys, not passwords

Set \`disablePasswordAuthentication: true\` and pass an SSH public key as a \`securestring\` parameter:

\`\`\`json
"linuxConfiguration": {
  "disablePasswordAuthentication": true,
  "ssh": { "publicKeys": [ { "keyData": "[parameters('sshPublicKey')]" } ] }
}
\`\`\`

## Parameterize the moving parts

\`vmSize\` and \`location\` change per environment — make them parameters with defaults. Everything else (names, subnet ref) can be computed \`variables\`, so one template serves dev, staging and prod.

## Security notes

- Attach a network security group and restrict SSH (22) to your office/VPN range.
- On production, prefer a bastion or just-in-time access over a raw public IP.

Open the VM deployment template and ask the workspace to "add a network security group allowing SSH" or "add a data disk", then diff the result.`,
};
