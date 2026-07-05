package main

import (
	"bytes"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"
)

// Define flags
var (
	mode    = flag.String("mode", "server", "Mode to run: 'server' or 'client'")
	port    = flag.String("port", "8080", "Port to run server on")
	servers = flag.String("servers", "", "Comma-separated list of server IP:port addresses for client mode")
	command = flag.String("command", "ping", "Command to send from client")
)

func main() {
	flag.Parse()

	if *mode == "server" {
		startServer()
	} else if *mode == "client" {
		runClient()
	} else {
		log.Fatalf("Unknown mode: %s", *mode)
	}
}

// startServer sets up an HTTP server that responds to /command
func startServer() {
	http.HandleFunc("/command", func(w http.ResponseWriter, r *http.Request) {
		// Read the command from the request body
		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "Failed to read body", http.StatusBadRequest)
			return
		}
		log.Printf("Received command: %s", body)
		fmt.Fprintf(w, "Received: %s", body)
	})

	log.Printf("Server listening on port %s", *port)
	log.Fatal(http.ListenAndServe(":"+*port, nil))
}

// runClient tries each server in order and sends a command to the first one that responds
func runClient() {
	if *servers == "" {
		log.Fatal("No servers specified")
	}
	serverList := strings.Split(*servers, ",")

	for _, addr := range serverList {
		url := fmt.Sprintf("http://%s/command", strings.TrimSpace(addr))
		log.Printf("Trying %s...", url)

		// Send the command as a POST request
		req, err := http.NewRequest("POST", url, bytes.NewBuffer([]byte(*command)))
		if err != nil {
			log.Printf("Failed to create request: %v", err)
			continue
		}
		req.Header.Set("Content-Type", "text/plain")

		client := http.Client{Timeout: 2 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			log.Printf("Connection failed: %v", err)
			continue
		}
		defer resp.Body.Close()
		respBody, _ := io.ReadAll(resp.Body)
		log.Printf("Server %s responded: %s", addr, string(respBody))
		return // Exit after first successful server
	}

	log.Println("No servers responded")
}
