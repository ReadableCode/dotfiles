# Using a Local Docker Registry

## Initial Setup - Allow insecure registries in Docker on each system that will push or pull from registry, only on systems using docker not containerd, you will know if the directory below doesnt exist

- Edit the Docker daemon configuration file if it exists. (If it doesnt exist skip tehse steps)

```bash
sudo nano /etc/docker/daemon.json
```

- Add the following lines to the file:

```json
{
  "insecure-registries" : ["192.168.86.179:5000"]
}
```

- Restart Docker:

```bash
sudo systemctl restart docker
```

- Verify the Docker daemon is running:

```bash
sudo systemctl status docker
```

## Initial setup - Allow insecure registies on K3S for systems that do not have docker

- Edit or create the K3S configuration file:

```bash
sudo nano /etc/rancher/k3s/registries.yaml
```

- Add the following lines to the file:

```yaml
mirrors:
  "192.168.86.179:5000":
    endpoint:
      - "http://192.168.86.179:5000"
```

- Quick command for all nodes including worker nodes and master:

```bash
sudo mkdir -p /etc/rancher/k3s && sudo tee /etc/rancher/k3s/registries.yaml > /dev/null <<EOF
mirrors:
  "192.168.86.179:5000":
    endpoint:
      - "http://192.168.86.179:5000"
EOF
sudo chown root:root /etc/rancher/k3s/registries.yaml && sudo chmod 644 /etc/rancher/k3s/registries.yaml
```

- Check the result

```bash
sudo cat /etc/rancher/k3s/registries.yaml
```

- Restart K3S on master node:

```bash
sudo systemctl restart k3s
```

- Restart K3S on worker nodes:

```bash
sudo systemctl restart k3s-agent
```

- Verify K3S is running:

```bash
sudo systemctl status k3s
```

## Building and Uploading an Image to the Local Registry

### 1. Build the Docker Image

- cd to the directory with the dockerfile

- Make sure your dockerignore file is set up to ignore the files you don't want to include in the image.

```bash
# Check the dockerignore file
cat .dockerignore
```

```bash
sudo docker build -t a_girls_guide_to_georgetown_image:latest .
```

- Verify that the built image is available locally:

```bash
sudo docker images
```

### 2. Tag the Docker Image

```bash
sudo docker tag a_girls_guide_to_georgetown_image:latest 192.168.86.179:5000/a_girls_guide_to_georgetown_image:latest
```

### 3. Push the Docker Image to the Local Registry

```bash
sudo docker push 192.168.86.179:5000/a_girls_guide_to_georgetown_image:latest
```

### 4. Verify the Image is in the Local Registry

```bash
curl http://192.168.86.179:5000/v2/_catalog
```

### 6. Pull the Image from the Local Registry

```bash
sudo docker pull 192.168.86.179:5000/a_girls_guide_to_georgetown_image:latest
```
