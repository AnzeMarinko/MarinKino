#!/bin/bash

# MarinKino Test Runner Script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC} $1"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Check if pytest is installed
check_pytest() {
    if ! command -v pytest &> /dev/null; then
        print_error "pytest is not installed"
        echo "Install it with: pip install pytest pytest-cov pytest-mock python-dotenv"
        exit 1
    fi
    print_success "pytest is installed"
}

# Run tests
run_tests() {
    local test_path=$1
    local coverage=$2
    
    print_header "Running Tests"
    
    if [ "$coverage" = "true" ]; then
        pytest "$test_path" -v --cov=src --cov-report=html --cov-report=term-missing
        print_success "Coverage report generated in htmlcov/index.html"
    else
        pytest "$test_path" -v
    fi
}

# Show usage
show_usage() {
    echo "MarinKino Test Runner"
    echo ""
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  all              Run all tests"
    echo "  auth             Run authentication tests"
    echo "  movies           Run movies tests"
    echo "  music            Run music tests"
    echo "  memes            Run memes tests"
    echo "  admin            Run admin tests"
    echo "  misc             Run miscellaneous tests"
    echo "  coverage         Run all tests with coverage report"
    echo "  quick            Run tests without coverage"
    echo "  help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 all"
    echo "  $0 auth"
    echo "  $0 coverage"
}

# Main
main() {
    case "${1:-help}" in
        all)
            check_pytest
            run_tests "tests/" false
            ;;
        auth)
            check_pytest
            run_tests "tests/test_auth_bp.py" false
            ;;
        movies)
            check_pytest
            run_tests "tests/test_movies_bp.py" false
            ;;
        music)
            check_pytest
            run_tests "tests/test_music_bp.py" false
            ;;
        memes)
            check_pytest
            run_tests "tests/test_memes_bp.py" false
            ;;
        admin)
            check_pytest
            run_tests "tests/test_admin_bp.py" false
            ;;
        misc)
            check_pytest
            run_tests "tests/test_misc_bp.py" false
            ;;
        coverage)
            check_pytest
            run_tests "tests/" true
            ;;
        quick)
            check_pytest
            run_tests "tests/" false
            ;;
        help)
            show_usage
            ;;
        *)
            print_error "Unknown option: $1"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
