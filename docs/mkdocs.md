# MKDOCS

## Check document structure

```bash
# list the doc files to make sure the docker command is working and files are structured correctly
docker run -v F:\HelloFresh\GDrive\Projects\na-finops:/content -p 8000:8000 -w /content --entrypoint ls -it spotify/techdocs
```

## Serve makedocs locally to test

```bash
# serve the mkdocs on localhost:8000
docker build -t na-finops-mkdocs -f Dockerfile-mkdocs .
# powershell
docker run -v ${PWD}:/content/ -p 8000:8000 -w /content/ -it na-finops-mkdocs serve -a 0.0.0.0:8000
# bash
docker run -v $(pwd):/content/ -p 8000:8000 -w /content/ -it na-finops-mkdocs serve -a 0.0.0.0:8000
```

## Build the mkdocs as an output: Site directory and PDF file

```bash
# build the mkdocs as an output
docker build -t na-finops-mkdocs -f Dockerfile-mkdocs .
# powershell
docker run -v ${PWD}:/content/ -w /content/ -it na-finops-mkdocs build
# bash
docker run -v $(pwd):/content/ -w /content/ -it na-finops-mkdocs build
```
