package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// Define patterns to search for
var patterns = []string{"sync-conflict", "~syncthing"}

func main() {
	// Default to current directory
	targetDir := "."

	// Check command-line arguments
	if len(os.Args) > 1 {
		targetDir = os.Args[1]
	}

	// Get absolute path
	startDir, err := filepath.Abs(targetDir)
	if err != nil {
		fmt.Println("Error getting absolute path:", err)
		os.Exit(1)
	}

	// Print working directory info
	fmt.Println("Scanning directory:", startDir)

	var foundItems []string

	// Walk through the directory structure and find matching files
	err = filepath.Walk(startDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Ignore permission errors
		}
		if !info.IsDir() {
			for _, pattern := range patterns {
				if strings.Contains(info.Name(), pattern) {
					foundItems = append(foundItems, path)
					break
				}
			}
		}
		return nil
	})

	if err != nil {
		fmt.Println("Error scanning directory:", err)
		os.Exit(1)
	}

	// Output found files
	if len(foundItems) > 0 {
		fmt.Printf("\nFound %d matching files in %s:\n", len(foundItems), startDir)
		for _, file := range foundItems {
			fmt.Println(file)
		}

		// Ask for confirmation before deletion
		fmt.Print("\nType 'delete' to remove these files, or press Enter to cancel: ")
		reader := bufio.NewReader(os.Stdin)
		confirm, _ := reader.ReadString('\n')
		confirm = strings.TrimSpace(confirm)

		if confirm == "delete" {
			for _, file := range foundItems {
				err := os.Remove(file)
				if err != nil {
					// Fix permission issues
					if runtime.GOOS == "windows" {
						fmt.Println("Retrying deletion with admin privileges:", file)
						_ = os.Chmod(file, 0777) // Modify permissions
						_ = os.Remove(file)      // Try deletion again
					} else {
						fmt.Println("Failed to delete:", file, err)
					}
				}
			}
			fmt.Println("Deleted all matching files.")
		} else {
			fmt.Println("Aborted. No files were deleted.")
		}
	} else {
		fmt.Println("No matching files found in", startDir)
	}
}
