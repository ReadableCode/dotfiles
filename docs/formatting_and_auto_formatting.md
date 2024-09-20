# Formatting

## Flake8

- To list and count the formatting issues with flake8:

  ```bash
  (flake8 | grep './' | head -n 20) 2>/dev/null && flake8 | grep './' | wc -l
  ```

  - To auto format with flake8:

    ```bash
    flake8 --ignore=E501,W503 --max-line-length=88 --exclude=src/proto
    ```

## Black

- To list and count the formatting issues with black:
  
  - To list changes black would make:

      ```bash
      black --check .
      ```

  - To auto format with black:

      ```bash
      black .
      ```

## Isort

- To list and count the formatting issues with isort:

  - To list changes isort would make:
  
    ```bash
    isort --profile black --check-only .
    ```
  
  - To auto format with isort:
  
    ```bash
    isort --profile black .
    ```

## MyPy

- To list and count the formatting issues with mypy:

  - Must be run from Project root directory on src directory

  - To see what changes need to be made:
  
    ```bash
    mypy src/.
    ```

  - To auto format with mypy:

    ```bash
    mypy src/. --strict
    ```

## Running precommit

- Install
  
    ```bash
    pre-commit install
    ```

- Run

  - To auto format with pre-commit:
  
    ```bash
    pre-commit run --all-files
    ```
