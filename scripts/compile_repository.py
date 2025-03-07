name: Compile Repository

on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:
    inputs:
      format:
        description: 'Format to compile (altstore, trollapps, scarlet, or empty for all)'
        required: false
        default: ''
        type: choice
        options:
          - ''
          - altstore
          - trollapps
          - scarlet

jobs:
  compile-repo:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
    
    - name: Run compilation
      run: |
        if [ -z "${{ github.event.inputs.format }}" ]; then
          python3 scripts/compile_repository.py
        else
          python3 scripts/compile_repository.py --format "${{ github.event.inputs.format }}"
        fi

    - name: Debug - List files
      run: |
        ls -la
        echo "Checking for JSON files:"
        ls -la *.json || echo "No JSON files found in root directory"

    - name: Commit and push changes
      run: |
        git config --global user.name "GitHub Actions"
        git config --global user.email "actions@github.com"
        git add *.json
        if git diff --staged --quiet; then
          echo "No changes to commit"
          exit 0  # Explicitly exit with success
        else
          git commit -m "chore: Update ${{ github.event.inputs.format || 'all' }} repository files [skip ci]"
          git push
        fi