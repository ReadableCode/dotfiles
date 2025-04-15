# Kubernetes K3S Mixed Cluster

## Raspberry Pi Specific Setup (host or node)

- If the machine is a raspberry pi do the following first:

```bash
sudo nano /boot/cmdline.txt
# if message about not editing file it has moved
sudo nano /boot/firmware/cmdline.txt
# then reboot
sudo reboot
```

- Edit the file adding this to the end of the existing single line, do not add a new line:

```bash
cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory
```

## Install Kubernetes on first machine

### Install K3S

```bash
# Make sure curl is installed
sudo apt install curl

# Install K3S
export K3S_KUBECONFIG_MODE="644"
curl -sfL https://get.k3s.io | sh -
```

- If you will be using a local or self hosted docker registry, follow this for setup: [Local Registries](../docs/docker_container_registry_local.md)

### Check K3S status

```bash
k3s kubectl get nodes
```

### Get Token and IP address

```bash
# Get the token other nodes will need in order to join
sudo cat /var/lib/rancher/k3s/server/node-token
# Get the IP address of the first machine
hostname -I | awk '{print $1}'
```

## Install K3S on other machines

```bash
# Make sure curl is installed
sudo apt install curl
# Install K3S
export K3S_KUBECONFIG_MODE="644"
curl -sfL https://get.k3s.io | K3S_URL=https://<IP>:6443 K3S_TOKEN=<TOKEN> sh -
```

- If you will be using a local or self hosted docker registry, follow this for setup: [Local Registries](../docs/docker_container_registry_local.md)

## Deploy HelloWorld

- Create a file like this one: [../application_configs/k3s/helloworld.yaml](../application_configs/k3s/helloworld.yaml)

- cd to the directory where the file is located

```bash
# Check the file
cat helloworld.yaml
# Deploy the file
kubectl apply -f helloworld.yaml
# Check the status
kubectl get pods
# Test the service
curl http://<any-node-ip>:31000
```

## Deploy an image to local container registry for K3S to use

- See detailed instructions in [Local Registries](../docs/docker_container_registry_local.md)

## Create secrets from an .env file

- cd to the directory where the .env file is located

```bash
# Check the file
cat .env
# Create the secret
kubectl create secret generic my-env-secrets --from-env-file=.env
# Check the secret
kubectl get secret my-env-secrets -o yaml
```

- You can now reference this secret and deploy it into a pod in its configuration file like this:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: busybox
spec:
  replicas: 1
  selector:
    matchLabels:
      app: busybox
  template:
    metadata:
      labels:
        app: busybox
    spec:
      containers:
        - name: busybox-container
          image: busybox
          command:
            [
              "sh",
              "-c",
              "echo UNRAID_IP=$UNRAID_IP && echo S3_ENDPOINT=$S3_ENDPOINT && sleep 3600",
            ]
          envFrom:
            - secretRef:
                name: my-env-secrets

```

- From the directory where the file is located, run the following command to deploy the file:

```bash
kubectl apply -f busybox.yaml
```

- Check the status of the pod:

```bash
kubectl get pods
```

- Check the logs of the pod:

```bash
kubectl logs busybox-<pod-id>
```

## Set up NFS strorage (unsecure and will be available to all machines on the network)

- Install NFS server on the first machine

```bash
sudo apt install nfs-kernel-server
```

- Create a directory for the NFS share

```bash
sudo mkdir -p /mnt/nfs_share
```

- Edit the exports file to add the share

```bash
sudo nano /etc/exports
```

- Add the following line to the end of the file

```bash
/mnt/nfs_share *(rw,sync,no_subtree_check,no_root_squash)
```
