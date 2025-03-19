package main

import (
	"bytes"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
)

// List of directories to skip
var skipDirs = []string{"personal_credentials", "hellofresh_credentials"}

// Run `git pull` on a repo and capture results
func gitPull(repo string, wg *sync.WaitGroup, results chan<- string, errors chan<- string, verbose bool) {
	defer wg.Done()

	if verbose {
		fmt.Println("[STARTING] Pulling repo:", repo)
	}

	cmd := exec.Command("git", "-C", repo, "pull")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err := cmd.Run()
	if err != nil {
		errors <- fmt.Sprintf("[FAILED] %s: %s", repo, strings.TrimSpace(stderr.String()))
		return
	}

	output := strings.TrimSpace(stdout.String())
	if output == "Already up to date." {
		results <- fmt.Sprintf("[NO CHANGES] %s", repo)
	} else {
		results <- fmt.Sprintf("[UPDATED] %s:\n%s", repo, output)
	}

	if verbose {
		fmt.Println("[DONE] Finished pulling repo:", repo)
	}
}

// Find all Git repositories in a directory with a specified depth
func findGitRepos(baseDir string, maxDepth int, verbose bool) []string {
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

		// Skip explicitly listed directories
		if contains(skipDirs, filepath.Base(path)) {
			if verbose {
				fmt.Println("[SKIPPING] Ignoring:", path)
			}
			return filepath.SkipDir
		}

		// **Ignore non-directory files**
		if !info.IsDir() {
			return nil
		}

		// **Check if this is a Git repo before applying depth limit**
		if isGitRepo(path) {
			if verbose {
				fmt.Println("[FOUND] Git repo detected:", path)
			}
			repos = append(repos, path)
			return filepath.SkipDir // Stop scanning inside this repo
		}

		// **Only enforce depth limit for non-Git directories**
		currentDepth := strings.Count(path, string(filepath.Separator))
		if maxDepth > 0 && (currentDepth-baseDepth) >= maxDepth {
			if verbose {
				fmt.Println("[DEPTH LIMIT] Stopping at:", path)
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

func main() {
	// Accept multiple paths with -path flag
	var repoPaths []string
	flag.Func("path", "Specify one or more paths to repos (space-separated or multiple -path flags)", func(s string) error {
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
	notGitRepos := make(chan string, len(repoPaths))

	for i, path := range repoPaths {
		absPath, err := filepath.Abs(path) // Convert relative to absolute
		if err != nil {
			fmt.Println("[ERROR] Invalid path:", path)
			continue
		}
		repoPaths[i] = absPath

		stat, err := os.Stat(path)
		if err != nil {
			fmt.Println("[ERROR] Invalid path:", path)
			continue
		}

		if stat.IsDir() {
			if *recursive {
				// Recursive directory search with depth limit
				foundRepos := findGitRepos(path, *depth, *verbose)
				repos = append(repos, foundRepos...)
			} else if isGitRepo(path) {
				// Single Git repo case
				repos = append(repos, path)
			} else {
				notGitRepos <- path
			}
		} else {
			fmt.Println("[ERROR] Skipping non-directory:", path)
		}
	}

	close(notGitRepos)

	if len(repos) == 0 {
		fmt.Println("[ERROR] No valid Git repos found")
		os.Exit(1)
	}

	// Prepare channels for results
	var wg sync.WaitGroup
	results := make(chan string, len(repos))
	errors := make(chan string, len(repos))
	skipped := make(chan string, len(repos))

	for _, repo := range repos {
		repoName := filepath.Base(repo)

		// Skip explicitly listed directories
		if contains(skipDirs, repoName) {
			skipped <- fmt.Sprintf("[SKIPPED] %s (In skip list)", repoName)
			continue
		}

		// Skip non-git directories
		if !isGitRepo(repo) {
			skipped <- fmt.Sprintf("[SKIPPED] %s (Not a git repo)", repoName)
			continue
		}

		wg.Add(1)
		go gitPull(repo, &wg, results, errors, *verbose)
	}

	wg.Wait()
	close(results)
	close(errors)
	close(skipped)

	// Output results
	fmt.Println("=== Pull Results ===")
	for res := range results {
		fmt.Println(res)
	}

	fmt.Println("\n=== Errors ===")
	for err := range errors {
		fmt.Println(err)
	}

	fmt.Println("\n=== Skipped ===")
	for skip := range skipped {
		fmt.Println(skip)
	}

	fmt.Println("\n=== Not a Git Repo ===")
	for notRepo := range notGitRepos {
		fmt.Println(notRepo)
	}
}
