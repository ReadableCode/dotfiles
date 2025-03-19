package main

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Directories and files to match
var dirPatterns = []string{
	"__pycache__", ".venv", "venv", "node_modules", ".mypy_cache",
	"target", "dist", "build", "builds", ".buildozer",
	"stable-diffusion-webui/models", "stable-diffusion-webui/extensions",
	"stable-diffusion-webui-amdgpu/models", "stable-diffusion-webui-amdgpu/extensions",
	"Something-Familiar/Library",
}

var filePatterns = []string{
	"sync-conflict", "~syncthing",
}

// Windows-specific function to force delete
func forceDeleteWindows(path string) error {
	cmd := exec.Command("cmd", "/c", "rmdir", "/s", "/q", path)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func main() {
	// Get target directory (default: current directory)
	targetDir := "."
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

	var foundDirs, foundFiles []string

	// Walk through directory to find matching items
	err = filepath.Walk(startDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil // Ignore permission errors
		}
		if info.IsDir() {
			for _, pattern := range dirPatterns {
				if strings.HasSuffix(path, pattern) {
					foundDirs = append(foundDirs, path)
					return filepath.SkipDir // Skip deeper search
				}
			}
		} else {
			for _, pattern := range filePatterns {
				if strings.Contains(info.Name(), pattern) {
					foundFiles = append(foundFiles, path)
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

	// Output found directories & files
	totalItems := len(foundDirs) + len(foundFiles)
	if totalItems > 0 {
		fmt.Printf("\nFound %d matching items:\n", totalItems)
		for _, dir := range foundDirs {
			fmt.Println("[DIR]  ", dir)
		}
		for _, file := range foundFiles {
			fmt.Println("[FILE] ", file)
		}

		// Ask for confirmation before deletion
		fmt.Print("\nType 'delete' to remove these items, or press Enter to cancel: ")
		reader := bufio.NewReader(os.Stdin)
		confirm, _ := reader.ReadString('\n')
		confirm = strings.TrimSpace(confirm)

		if confirm == "delete" {
			// Delete files first
			for _, file := range foundFiles {
				err := os.Remove(file)
				if err != nil {
					fmt.Println("Failed to delete:", file, err)
				}
			}
			// Delete directories
			for _, dir := range foundDirs {
				err := os.RemoveAll(dir)
				if err != nil {
					fmt.Println("os.RemoveAll failed, trying Windows rmdir:", dir)
					err = forceDeleteWindows(dir)
				}
				if err != nil {
					fmt.Println("Failed to delete:", dir, err)
				} else {
					fmt.Println("Deleted:", dir)
				}
			}
		} else {
			fmt.Println("Aborted. No files or directories were deleted.")
		}
	} else {
		fmt.Println("No matching files or directories found in", startDir)
	}
}
