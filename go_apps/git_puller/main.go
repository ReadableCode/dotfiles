package main

import (
	"bytes"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
)

// Run `git pull` on a repo and capture results
func gitPull(
	repo string,
	wg *sync.WaitGroup,
	results chan<- string,
	pulled chan<- string,
	errors chan<- string,
	noChanges chan<- string,
	verbose bool,
) {
	// Defer the WaitGroup Done call to ensure it runs after the function completes
	defer wg.Done()

	absRepo, err := filepath.Abs(repo)
	if err != nil {
		errors <- fmt.Sprintf("[ERROR] Failed to resolve path: %s", repo)
		return
	}

	if verbose {
		fmt.Println("[STARTING] Pulling repo:", absRepo)
	}

	// run the git command with -C to change to the repo directory
	cmd := exec.Command("git", "-C", absRepo, "pull")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()
	output := strings.TrimSpace(stdout.String())
	errorMsg := strings.TrimSpace(stderr.String())

	// Detect authentication failure
	if strings.Contains(errorMsg, "Username for 'https://github.com'") || strings.Contains(errorMsg, "fatal: could not read Username") {
		errors <- fmt.Sprintf("[AUTH REQUIRED] %s (Skipping)", absRepo)
		return
	}

	if err != nil {
		errors <- fmt.Sprintf("[FAILED] %s: %s", absRepo, errorMsg)
		return
	}

	if output == "Already up to date." {
		noChanges <- fmt.Sprintf("[NO CHANGES] %s", absRepo)
	} else {
		results <- fmt.Sprintf("[UPDATED] %s:\n%s", absRepo, output)
		pulled <- fmt.Sprintf("[PULLED] %s", absRepo)
	}

	if verbose {
		fmt.Println("[DONE] Finished pulling repo:", absRepo)
	}
}

// Find all Git repositories in a directory with a specified depth
func findGitRepos(
	baseDir string,
	maxDepth int,
	skipped *[]string,
	notGitRepos *[]string,
	verbose bool,
	dynamicSkips []string,
) []string {
	var repos []string
	baseDepth := strings.Count(baseDir, string(filepath.Separator))

	if verbose {
		fmt.Println("[SCANNING] Searching for Git repositories in:", baseDir)
	}

	err := filepath.Walk(baseDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			fmt.Println("[ERROR] Accessing:", path, err)
			return nil
		}

		absPath, _ := filepath.Abs(path)

		// Skip explicitly listed directories
		if contains(dynamicSkips, filepath.Base(path)) {
			*skipped = append(*skipped, fmt.Sprintf("[SKIPPED] %s (In dynamic skip list)", absPath))
			return filepath.SkipDir
		}

		// Ignore non-directory files
		if !info.IsDir() {
			return nil
		}

		// Check if this is a Git repo before applying depth limit
		if isGitRepo(path) {
			if verbose {
				fmt.Println("[FOUND] Git repo detected:", absPath)
			}
			repos = append(repos, absPath)
			return filepath.SkipDir // Stop scanning inside this repo
		}

		// If it's a directory and not a Git repo, log it
		*notGitRepos = append(*notGitRepos, fmt.Sprintf("[NOT A REPO] %s", absPath))

		// Enforce depth limit for non-Git directories
		currentDepth := strings.Count(path, string(filepath.Separator))
		if maxDepth > 0 && (currentDepth-baseDepth) >= maxDepth {
			if verbose {
				fmt.Println("[DEPTH LIMIT] Stopping at:", absPath)
			}
			return filepath.SkipDir
		}

		return nil
	})

	if err != nil {
		fmt.Println("[ERROR] Failed to scan directory:", baseDir, err)
	}

	return repos
}

// Check if a directory is a Git repo
func isGitRepo(path string) bool {
	_, err := os.Stat(filepath.Join(path, ".git"))
	return err == nil
}

// Helper function to check if a string is in a slice
func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

func readSkipList(baseDir string) []string {
	filePath := filepath.Join(baseDir, ".skiprepos")
	file, err := os.Open(filePath)
	if err != nil {
		return nil
	}
	defer file.Close()

	var filtered []string
	buf := make([]byte, 4096)
	var content strings.Builder
	for {
		n, err := file.Read(buf)
		if err != nil && err != io.EOF {
			return nil
		}
		if n == 0 {
			break
		}
		content.Write(buf[:n])
	}

	lines := strings.Split(content.String(), "\n")
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed != "" {
			filtered = append(filtered, trimmed)
		}
	}
	return filtered
}

func main() {
	var repoPaths []string
	flag.Func("path", "Specify one or more paths to repos", func(s string) error {
		if runtime.GOOS == "windows" {
			repoPaths = append(repoPaths, strings.Split(s, ";")...) // Handle Windows `;` separation
		} else {
			repoPaths = append(repoPaths, strings.Fields(s)...) // Handle Linux/macOS space-separated paths
		}
		return nil
	})

	recursive := flag.Bool("r", false, "Enable recursive search for git repos in the directory")
	verbose := flag.Bool("v", false, "Enable verbose output (logs when starting/ending a repo)")
	depth := flag.Int("depth", 1, "Recursion depth when using -r (default: 1, -1 for unlimited)")
	flag.Parse()

	if len(repoPaths) == 0 {
		fmt.Println("[ERROR] Please provide at least one path using -path")
		os.Exit(1)
	}

	var repos []string
	var skipped []string
	var notGitRepos []string

	for _, path := range repoPaths {
		absPath, err := filepath.Abs(path)
		if err != nil {
			fmt.Println("[ERROR] Invalid path:", path)
			continue
		}

		stat, err := os.Stat(absPath)
		if err != nil || !stat.IsDir() {
			fmt.Println("[ERROR] Skipping invalid or non-directory:", absPath)
			continue
		}

		var dynamicSkips []string
		if *recursive {
			dynamicSkips = readSkipList(absPath)
			repos = append(repos, findGitRepos(absPath, *depth, &skipped, &notGitRepos, *verbose, dynamicSkips)...)
		} else {
			if isGitRepo(absPath) {
				repos = append(repos, absPath)
			} else {
				notGitRepos = append(notGitRepos, fmt.Sprintf("[NOT A REPO] %s", absPath))
			}
		}
	}

	var wg sync.WaitGroup
	results := make(chan string, len(repos))
	pulled := make(chan string, len(repos))
	errors := make(chan string, len(repos))
	noChanges := make(chan string, len(repos))

	for _, repo := range repos {
		wg.Add(1)
		go gitPull(repo, &wg, results, pulled, errors, noChanges, *verbose)
	}

	wg.Wait()
	close(results)
	close(pulled)
	close(errors)
	close(noChanges)

	fmt.Println("\n=== No Changes ===")
	for noChange := range noChanges {
		fmt.Println(noChange)
	}

	fmt.Println("\n=== Pull Results ===")
	for res := range results {
		fmt.Println(res)
	}

	fmt.Println("\n=== Skipped Directories ===")
	for _, skip := range skipped {
		fmt.Println(skip)
	}

	fmt.Println("\n=== Pulled Repos ===")
	for pulledRepo := range pulled {
		fmt.Println(pulledRepo)
	}

	fmt.Println("\n=== Not a Git Repo ===")
	for _, notRepo := range notGitRepos {
		fmt.Println(notRepo)
	}

	fmt.Println("\n=== Errors ===")
	for err := range errors {
		fmt.Println(err)
	}
}
