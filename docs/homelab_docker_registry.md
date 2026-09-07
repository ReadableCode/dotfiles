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

#### Building for a single architecture

```bash
sudo docker build -t a_girls_guide_to_georgetown_image:latest .
```

- Verify that the built image is available locally:

```bash
sudo docker images
```

- Tag the Docker Image

```bash
sudo docker tag a_girls_guide_to_georgetown_image:latest 192.168.86.179:5000/a_girls_guide_to_georgetown_image:latest
```

- Push the Docker Image to the Local Registry

```bash
sudo docker push 192.168.86.179:5000/a_girls_guide_to_georgetown_image:latest
```

#### Building for multiple architectures

- Enable buildx if you want to build for multiple architectures.

```bash
export DOCKER_CLI_EXPERIMENTAL=enabled
export DOCKER_BUILDKIT=1
sudo apt install docker-buildx
```

- Turn on experimental features in Docker.

```bash
sudo nano /etc/docker/daemon.json
```

- Add the following lines to the file or add to the existing dictionary if it exists:

```json
{
  "experimental": true
}
```

- Edit or create a config file to be used by builder:

```bash
sudo mkdir -p /etc/buildkit
sudo nano /etc/buildkit/buildkitd.toml
```

- Put the following lines in the file:

```toml
[registry."192.168.86.179:5000"]
    http = true
    insecure = true
```

- Create the builder

```bash
sudo docker buildx create --name my-multi-builder --config /etc/buildkit/buildkitd.toml --use
```

- Check buildx availability:

```bash
sudo docker buildx version
sudo docker buildx ls
```

- Build the image for multiple architectures.

```bash
sudo docker buildx build --platform linux/arm64,linux/amd64 --push -t 192.168.86.179:5000/a_girls_guide_to_georgetown_image:latest .
```

### 2. Verify the Image is in the Local Registry

```bash
curl http://192.168.86.179:5000/v2/_catalog
```

### 3. Pull the Image from the Local Registry

```bash
sudo docker pull 192.168.86.179:5000/a_girls_guide_to_georgetown_image:latest
```
