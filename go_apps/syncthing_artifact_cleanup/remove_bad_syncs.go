package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// Patterns to match
var patterns = []string{
	"__pycache__", ".venv", "venv", "node_modules", ".mypy_cache",
	"target", "dist", "build", "builds", ".buildozer",
	"stable-diffusion-webui/models", "stable-diffusion-webui/extensions",
	"stable-diffusion-webui-amdgpu/models", "stable-diffusion-webui-amdgpu/extensions",
	"Something-Familiar/Library",
}

func main() {
	// Get folder from command-line argument (default to current directory)
	var targetDir string
	if len(os.Args) > 1 {
		targetDir = os.Args[1]
	} else {
		targetDir = "." // Default to current directory
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

	// Walk through the directory structure
	err = filepath.Walk(startDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Ignore permission errors
		}
		// Check if the directory matches any of the patterns
		if info.IsDir() {
			for _, pattern := range patterns {
				if strings.HasSuffix(path, pattern) {
					foundItems = append(foundItems, path)
					return filepath.SkipDir // Skip further traversal in this directory
				}
			}
		}
		return nil
	})

	if err != nil {
		fmt.Println("Error walking through directory:", err)
		os.Exit(1)
	}

	// Output found directories
	if len(foundItems) > 0 {
		fmt.Println("\nFound the following directories:")
		for _, item := range foundItems {
			fmt.Println(item)
		}

		// Ask for confirmation
		fmt.Print("\nType 'delete' to remove these directories, or press Enter to cancel: ")
		reader := bufio.NewReader(os.Stdin)
		confirm, _ := reader.ReadString('\n')
		confirm = strings.TrimSpace(confirm)

		// If user confirms deletion
		if confirm == "delete" {
			for _, item := range foundItems {
				err := os.RemoveAll(item)
				if err != nil {
					// Fix permission issues
					if runtime.GOOS == "windows" {
						fmt.Println("Retrying deletion with admin privileges:", item)
						_ = os.Chmod(item, 0777) // Attempt to modify permissions
						_ = os.RemoveAll(item)   // Try deletion again
					} else {
						fmt.Println("Failed to delete:", item, err)
					}
				}
			}
			fmt.Println("Deleted all matching directories.")
		} else {
			fmt.Println("Aborted. No directories were deleted.")
		}
	} else {
		fmt.Println("No matching directories found in", startDir)
	}
}
