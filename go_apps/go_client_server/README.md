# Go Client Server App

## Run the server

```bash
go run main.go --mode=server --port=8080
```

## Run the client

```bash
go run main.go --mode=client --servers=127.0.0.1:8080,192.168.1.10:8080 --command="ping"
```

## Use curl as the client

- Linux

```bash
curl -X POST http://127.0.0.1:8080/command -d "ping"
```

- Windows

```bash
Invoke-WebRequest -Uri http://127.0.0.1:8080/command -Method POST -Body "ping"
```
